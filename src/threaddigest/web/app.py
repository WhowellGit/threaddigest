"""The FastAPI application: one engine, one Jinja environment, one perimeter.

``create_app`` is the composition root of the web layer, the way ``cli`` is the composition
root of the process: everything a route needs is built here and read back through
``web/deps.py``, so no module below reaches for a global.

**One engine per process** (UI design review § 0, N-07). The lifespan opens it from the
resolved data directory and disposes it on shutdown. A caller may inject one instead --
that is what the test suite does with a temp database -- and an injected engine is left
alone at shutdown, because whoever made it owns it.

**The Jinja environment is built here, not by Starlette.** ``Jinja2Templates(directory=...)``
constructs ``jinja2.Environment(loader=..., autoescape=select_autoescape())`` with the
*default* ``Undefined``, which renders a misspelled or missing variable as an empty string.
The plan's tech-stack row says ``StrictUndefined``, and the point is exactly that a page must
not quietly print nothing where a number was meant, so the environment is constructed here
and handed over as ``env=``. Autoescape is on for every template, not only the ones with an
HTML suffix.

**No documentation routes.** ``/docs``, ``/redoc`` and ``/openapi.json`` are turned off:
this is an operator page, not an API, and every route a browser can reach is one more route
the structural tests must reason about.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from sqlalchemy import Engine
from starlette.templating import Jinja2Templates

from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.settings import Settings
from threaddigest.web import filters
from threaddigest.web.middleware import HostCheck, SecurityHeaders
from threaddigest.web.routes import reports, runs

__all__ = ["STATIC_DIR", "STATIC_MOUNT", "TEMPLATES_DIR", "build_templates", "create_app"]

_PACKAGE_ROOT: Final = Path(__file__).resolve().parent
TEMPLATES_DIR: Final = _PACKAGE_ROOT / "templates"
STATIC_DIR: Final = _PACKAGE_ROOT / "static"

#: The URL prefix the stylesheet is served under; ``base.html`` reaches it by ``url_for``.
STATIC_MOUNT: Final = "/static"


def build_templates(directory: Path = TEMPLATES_DIR) -> Jinja2Templates:
    """The template environment: strict undefined, autoescape everywhere, shared filters."""
    env = Environment(
        loader=FileSystemLoader(directory),
        undefined=StrictUndefined,
        autoescape=select_autoescape(default_for_string=True, default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    filters.register(env)
    return Jinja2Templates(env=env)


def create_app(*, settings: Settings, engine: Engine | None = None) -> FastAPI:
    """Build the application. ``engine`` injected means the caller owns its lifetime."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        owned = engine is None
        if owned:
            application.state.engine = engine_for(db_path_for(settings.data_dir))
        try:
            yield
        finally:
            if owned:
                application.state.engine.dispose()

    app = FastAPI(
        title="Thread Digest",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.templates = build_templates()
    if engine is not None:
        # Set outside the lifespan too, so an injected engine is reachable by a caller that
        # never starts the application (a route function driven directly in a test).
        app.state.engine = engine
    # Added innermost first: the Host refusal travels back out through SecurityHeaders, so
    # even a rejected request carries the content-security policy.
    app.add_middleware(HostCheck)
    app.add_middleware(SecurityHeaders)
    app.mount(STATIC_MOUNT, StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(runs.router)
    app.include_router(reports.router)
    return app
