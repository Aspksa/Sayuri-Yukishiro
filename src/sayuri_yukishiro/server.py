from __future__ import annotations

import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .database import CoreDatabase
from .paths import WEB_DIR, project_version


class SayuriHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], db: CoreDatabase):
        self.db = db
        super().__init__(server_address, SayuriHandler)


class SayuriHandler(BaseHTTPRequestHandler):
    server_version = "SayuriYukishiro/0.1.0"

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

        if path == "/api/health":
            self._json(
                {
                    "status": "ok",
                    "project": "Sayuri Yukishiro",
                    "version": project_version(),
                    "pid": os.getpid(),
                }
            )
            return

        if path == "/api/modules":
            self._json({"modules": self.app_server.db.list_modules()})
            return

        if path == "/api/system":
            self._json(
                {
                    "project": "Sayuri Yukishiro",
                    "version": project_version(),
                    "database": str(self.app_server.db.path),
                    "database_check": self.app_server.db.quick_check(),
                    "module_count": len(self.app_server.db.list_modules()),
                }
            )
            return

        relative = "index.html" if path == "/" else path.lstrip("/")
        self._serve_file(relative)

    def log_message(self, format: str, *args) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    db = CoreDatabase()
    db.initialize()
    db.append_event("core.start", {"host": host, "port": port}, module_id="core")

    server = SayuriHTTPServer((host, port), db)
    print(f"Sayuri Yukishiro {project_version()} listening on http://{host}:{port}")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        db.append_event("core.stop", {"host": host, "port": port}, module_id="core")
        server.server_close()
