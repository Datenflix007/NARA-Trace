from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from naratrace import __version__
from naratrace.api.routes import api_router
from naratrace.core.config import get_settings
from naratrace.core.paths import ensure_local_directories
from naratrace.database.init import init_database
from naratrace.database.session import dispose_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    paths = ensure_local_directories()
    init_database(paths=paths)
    app.state.local_paths = paths
    try:
        yield
    finally:
        dispose_database()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NARATrace",
        description="Lokale, quellennahe Personensuche im National Archives Catalog",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(api_router)
    mount_frontend(app)
    return app


def mount_frontend(app: FastAPI) -> None:
    dist_dir = frontend_dist_dir()
    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    demo_dir = dist_dir / "demo"
    if not demo_dir.exists():
        demo_dir = frontend_public_dir() / "demo"
    if demo_dir.exists():
        app.mount("/demo", StaticFiles(directory=demo_dir), name="demo")

    @app.get("/", include_in_schema=False)
    async def index():
        index_file = dist_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return HTMLResponse(fallback_index_html())


def frontend_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def frontend_public_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / "public"


def fallback_index_html() -> str:
    return """
<!doctype html>
<html lang="de">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>NARATrace</title>
    <style>
      :root {
        color-scheme: light;
        --paper: #f6efe2;
        --paper-deep: #eadbc2;
        --ink: #252321;
        --muted: #665d52;
        --accent: #8b3f2f;
        --line: #d8c8ad;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: var(--paper);
        color: var(--ink);
      }
      header, main, footer { width: min(1080px, calc(100% - 32px)); margin: 0 auto; }
      header {
        padding: 28px 0 18px;
        border-bottom: 1px solid var(--line);
      }
      .source {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        color: var(--muted);
        font-size: 14px;
      }
      .badge {
        border: 1px solid var(--accent);
        color: var(--accent);
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
      }
      main { padding: 56px 0; }
      h1 { font-size: clamp(34px, 6vw, 64px); line-height: 1; margin: 0 0 12px; letter-spacing: 0; }
      p { max-width: 780px; line-height: 1.65; font-size: 18px; color: var(--muted); }
      .panel {
        margin-top: 28px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.42);
        border-radius: 8px;
        padding: 18px;
      }
      dl {
        display: grid;
        grid-template-columns: minmax(140px, 220px) 1fr;
        gap: 10px 18px;
        margin: 0;
      }
      dt { font-weight: 700; }
      dd { margin: 0; color: var(--muted); }
      a { color: var(--accent); font-weight: 700; }
      footer {
        border-top: 1px solid var(--line);
        padding: 18px 0 30px;
        color: var(--muted);
        font-size: 14px;
      }
    </style>
  </head>
  <body>
    <header>
      <div class="source">
        <span>Datenquelle: U.S. National Archives and Records Administration - National Archives Catalog</span>
        <span class="badge">NARA Catalog</span>
      </div>
    </header>
    <main>
      <h1>NARATrace</h1>
      <p>Lokale, quellennahe Personensuche im National Archives Catalog. Diese erste lokale Startseite bestätigt, dass Backend, Datenverzeichnis und SQLite-Initialisierung laufen.</p>
      <p>NARATrace unterstützt historische Archivforschung. Ergebnisse aus OCR und automatischem Matching sind Forschungshinweise und keine gesicherten Identifizierungen.</p>
      <section class="panel" aria-label="Systemstatus">
        <dl>
          <dt>Status</dt>
          <dd>FastAPI läuft lokal</dd>
          <dt>Health-Endpunkt</dt>
          <dd><a href="/api/health">/api/health</a></dd>
          <dt>API-Dokumentation</dt>
          <dd><a href="/docs">/docs</a></dd>
        </dl>
      </section>
    </main>
    <footer>
      NARATrace ist ein unabhängiges, inoffizielles Forschungswerkzeug. Es steht nicht in Verbindung mit der U.S. National Archives and Records Administration und wird nicht von NARA betrieben oder unterstützt.
    </footer>
  </body>
</html>
"""


app = create_app()
