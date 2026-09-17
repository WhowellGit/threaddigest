"""What a route asks for, and the seam a test replaces.

Three dependencies, each returning one thing :func:`web.app.create_app` put on
``app.state``: the engine, the resolved settings, and the template environment. They exist
so a route declares what it needs instead of reaching into ``request.app.state`` itself, and
so a test can replace any of them through ``app.dependency_overrides`` -- the seam the UI
design review's § 8 names for the database session and the collaborators around it.

The annotated aliases at the bottom are what routes actually write, so a signature reads
``engine: EngineDep`` rather than repeating ``Annotated[Engine, Depends(get_engine)]``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from starlette.templating import Jinja2Templates

from threaddigest.settings import Settings

__all__ = [
    "EngineDep",
    "SettingsDep",
    "TemplatesDep",
    "get_engine",
    "get_settings",
    "get_templates",
]


def get_engine(request: Request) -> Engine:
    """The one engine this process opened (UI review § 0: one engine per process)."""
    engine: Engine = request.app.state.engine
    return engine


def get_settings(request: Request) -> Settings:
    """The settings the CLI resolved before it started the server."""
    settings: Settings = request.app.state.settings
    return settings


def get_templates(request: Request) -> Jinja2Templates:
    """The Jinja environment built once in :func:`web.app.create_app`."""
    templates: Jinja2Templates = request.app.state.templates
    return templates


EngineDep = Annotated[Engine, Depends(get_engine)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
TemplatesDep = Annotated[Jinja2Templates, Depends(get_templates)]
