from __future__ import annotations

import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .core.runtime import SystemCore
from .paths import WEB_DIR, project_version


class SayuriHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], core: SystemCore):
        self.core = core
        super().__init__(server_address, SayuriHandler)


class SayuriHandler(BaseHTTPRequestHandler):
    server_version = "SayuriYukishiro/0.2.0"

    @property
    def app_server(self) -> SayuriHTTPServer:
        return self.server  # type: ignore[return-value]

    def _json(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, relative: str) -> None:
        root = WEB_DIR.resolve()
        target = (root / relative).resolve()
        if target != root and root not in target.parents:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        data = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        core = self.app_server.core

        if path == "/api/health":
            status = core.status()
            overall = status["health"]["overall"]
            self._json(
                {
                    "status": "ok" if overall == "healthy" else overall,
                    "project": "Sayuri Yukishiro",
                    "version": project_version(),
                    "core_version": status["core_version"],
                    "pid": os.getpid(),
                }
            )
            return

        if path == "/api/core":
            self._json(core.status())
            return

        if path == "/api/core/recovery":
            self._json({"tasks": core.api.recoverable_tasks()})
            return

        if path == "/api/core/jobs":
            self._json({"jobs": core.jobs.snapshot()})
            return

        if path == "/api/modules":
            self._json({"modules": core.db.list_modules()})
            return

        if path == "/api/system":
            core_status = core.status()
            self._json(
                {
                    "project": "Sayuri Yukishiro",
                    "version": project_version(),
                    "core_version": core_status["core_version"],
                    "core_health": core_status["health"]["overall"],
                    "database": str(core.db.path),
                    "database_check": core_status["database_check"],
                    "module_count": len(core.db.list_modules()),
                    "recoverable_tasks": core_status["recoverable_tasks"],
                }
            )
            return

        relative = "index.html" if path == "/" else path.lstrip("/")
        self._serve_file(relative)

    def log_message(self, format: str, *args) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    core = SystemCore()
    core.start()
    server = SayuriHTTPServer((host, port), core)
    print(
        f"Sayuri Yukishiro {project_version()} / core {core.CORE_VERSION} "
        f"listening on http://{host}:{port}"
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        core.stop()
