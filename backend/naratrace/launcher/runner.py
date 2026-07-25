from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import webbrowser

import httpx
import uvicorn

from naratrace.core.config import get_settings, reset_settings_cache
from naratrace.core.paths import ensure_local_directories
from naratrace.database.init import init_database

LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    validate_host(args.host, args.allow_non_localhost)
    ensure_port_available(args.host, args.port)
    apply_cli_overrides(args)

    paths = ensure_local_directories()
    init_database(paths=paths)

    base_url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        start_browser_thread(base_url)

    uvicorn.run(
        "naratrace.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=args.reload,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m naratrace")
    parser.add_argument("--host", default=settings.host, help="Bind host. Standard: 127.0.0.1")
    parser.add_argument("--port", type=int, default=settings.port, help="Bind port. Standard: 8765")
    parser.add_argument("--log-level", default=settings.log_level, help="Uvicorn log level")
    parser.add_argument("--reload", action="store_true", help="Enable Uvicorn reload for development")
    parser.add_argument("--no-browser", action="store_true", help="Start server without opening a browser")
    parser.add_argument(
        "--allow-non-localhost",
        action="store_true",
        help="Allow binding to a non-localhost interface. Disabled by default for local-only operation.",
    )
    return parser.parse_args(argv)


def apply_cli_overrides(args: argparse.Namespace) -> None:
    os.environ["NARATRACE_HOST"] = str(args.host)
    os.environ["NARATRACE_PORT"] = str(args.port)
    os.environ["NARATRACE_LOG_LEVEL"] = str(args.log_level)
    reset_settings_cache()


def validate_host(host: str, allow_non_localhost: bool) -> None:
    if host in LOCAL_HOSTS:
        return
    if allow_non_localhost:
        return
    raise SystemExit(
        "NARATrace bindet standardmäßig nur an 127.0.0.1. "
        "Nutze --allow-non-localhost nur bewusst für Entwicklungsfälle."
    )


def ensure_port_available(host: str, port: int) -> None:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError as exc:
        raise SystemExit(
            f"NARATrace kann nicht auf {host}:{port} starten, weil der Port bereits belegt ist. "
            "Beende den belegenden Dienst oder nutze für Entwicklung bewusst --port <anderer-port>."
        ) from exc


def start_browser_thread(base_url: str) -> None:
    thread = threading.Thread(target=open_browser_when_ready, args=(base_url,), daemon=True)
    thread.start()


def open_browser_when_ready(base_url: str, timeout_seconds: int = 30) -> None:
    health_url = f"{base_url}/api/health"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.get(health_url, timeout=2.0)
            if response.status_code == 200:
                webbrowser.open(base_url)
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
