"""Schema golden (``schema.sql``) and runtime schema fingerprint.

One normalizer, applied to both sides. ``dump_schema`` reads ``sqlite_master`` from a live
database and renders each object through :func:`normalize_ws`; ``fingerprint`` applies the
same normalizer line by line to any DDL text, so the fingerprint of a live database equals
the fingerprint of the packaged ``schema.sql`` exactly when their schemas agree. There is no
stored constant to drift.

Because SQLite discards column comments, the dump ends with a generated
``-- COLUMN COMMENTS`` section taken from the SQLAlchemy metadata: ``schema.sql`` doubles as
the data dictionary.

Regenerate with ``uv run python -m insightminer.db.schema_dump``.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from fnmatch import fnmatchcase
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from insightminer.db.engine import engine_for
from insightminer.db.schema import Base

__all__ = [
    "SCHEMA_SQL",
    "alembic_config",
    "canonical",
    "dump_schema",
    "fingerprint",
    "migrate_to_head",
    "normalize_ws",
    "write_schema_sql",
]

_DB_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = _DB_DIR / "migrations"
ALEMBIC_INI = _DB_DIR.parents[2] / "alembic.ini"
SCHEMA_SQL = _DB_DIR / "schema.sql"

_TYPE_ORDER: dict[str, int] = {"table": 0, "view": 1, "index": 2, "trigger": 3}
#: sqlite_master names left out of the dump: SQLite internals, Alembic batch temporaries and
#: the FTS5 shadow tables (their DDL is an implementation detail of the FTS5 module).
EXCLUDED_NAME_PATTERNS: tuple[str, ...] = (
    "sqlite_*",
    "_alembic_tmp_*",
    "*_fts_data",
    "*_fts_idx",
    "*_fts_content",
    "*_fts_docsize",
    "*_fts_config",
)
_QUOTE_CLOSERS: dict[str, str] = {"'": "'", '"': '"', "`": "`", "[": "]"}


def alembic_config(db_url: str | None = None) -> Config:
    """Alembic ``Config`` bound to this package's migrations regardless of the cwd."""
    cfg = Config(str(ALEMBIC_INI)) if ALEMBIC_INI.exists() else Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    if db_url is not None:
        # configparser interpolation: a literal percent sign must be doubled.
        cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return cfg


def migrate_to_head(engine: Engine) -> None:
    """Upgrade the database behind ``engine`` to the head revision through the Alembic API."""
    cfg = alembic_config()
    cfg.attributes["connection"] = engine
    command.upgrade(cfg, "head")


def normalize_ws(sql: str) -> str:
    """Collapse runs of whitespace to one space outside quoted regions; strip the ends.

    Quoted regions (``'…'``, ``"…"``, `` `…` ``, ``[…]``) are copied verbatim, doubled
    closing quotes included, so a literal or identifier never changes meaning.
    """
    out: list[str] = []
    pending_space = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch in _QUOTE_CLOSERS:
            closer = _QUOTE_CLOSERS[ch]
            j = i + 1
            while j < n:
                if sql[j] == closer:
                    if closer != "]" and j + 1 < n and sql[j + 1] == closer:
                        j += 2
                        continue
                    break
                j += 1
            if pending_space and out:
                out.append(" ")
            pending_space = False
            out.append(sql[i : j + 1])
            i = j + 1
        elif ch.isspace():
            pending_space = True
            i += 1
        else:
            if pending_space and out:
                out.append(" ")
            pending_space = False
            out.append(ch)
            i += 1
    return "".join(out)


def canonical(ddl_text: str) -> str:
    """The fingerprinted form: every line normalized, empty lines dropped, ``\\n`` joined."""
    lines = (normalize_ws(line) for line in ddl_text.splitlines())
    return "\n".join(line for line in lines if line)


def fingerprint(ddl_text: str) -> str:
    """SHA-256 of :func:`canonical` (``ddl_text``); line endings and indentation do not matter."""
    return hashlib.sha256(canonical(ddl_text).encode("utf-8")).hexdigest()


def _head_revision(engine: Engine) -> str:
    if "alembic_version" not in inspect(engine).get_table_names():
        return "(none)"
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    return ",".join(sorted(rows)) if rows else "(none)"


def _schema_objects(engine: Engine) -> list[tuple[str, str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE type IN ('table', 'view', 'index', 'trigger') AND sql IS NOT NULL"
            )
        ).all()
    kept = [
        (str(type_), str(name), str(sql))
        for type_, name, sql in rows
        if not any(fnmatchcase(str(name), pattern) for pattern in EXCLUDED_NAME_PATTERNS)
    ]
    kept.sort(key=lambda row: (_TYPE_ORDER[row[0]], row[1]))
    return kept


def _column_comment_lines() -> list[str]:
    lines: list[str] = []
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        for column in table.columns:
            comment = column.comment or ""
            lines.append(f"-- {table.name}.{column.name}: {comment}")
    return lines


def dump_schema(engine: Engine) -> str:
    """Render the live schema as normalized DDL plus the column-comment data dictionary.

    Objects are ordered table, view, index, trigger, then by name; each statement is one
    line ending in ``;``. The result is a fixed point of :func:`canonical`, so writing it
    to ``schema.sql`` and fingerprinting the file gives the same hash as the live database.
    """
    parts: list[str] = [
        f"-- head: {_head_revision(engine)}",
        "-- generated by `python -m insightminer.db.schema_dump`; do not edit by hand",
        "",
    ]
    parts.extend(f"{normalize_ws(sql)};" for _type, _name, sql in _schema_objects(engine))
    parts.extend(["", "-- COLUMN COMMENTS", *_column_comment_lines()])
    return canonical("\n".join(parts)) + "\n"


def write_schema_sql(path: Path = SCHEMA_SQL) -> str:
    """Migrate a throw-away database to head, dump it, write ``path``; return the text."""
    with tempfile.TemporaryDirectory(prefix="insightminer-schema-") as tmp:
        engine = engine_for(Path(tmp) / "schema.db")
        try:
            migrate_to_head(engine)
            rendered = dump_schema(engine)
        finally:
            engine.dispose()
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return rendered


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else SCHEMA_SQL
    rendered = write_schema_sql(target)
    sys.stdout.write(
        f"wrote {target} ({len(rendered.splitlines())} lines) {fingerprint(rendered)}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
