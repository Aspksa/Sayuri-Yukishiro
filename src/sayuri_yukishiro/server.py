from __future__ import annotations

import json
import mimetypes
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse

from .cognitive.engine import CognitiveCore
from .core.runtime import SystemCore
from .modules.runtime import ModuleRuntime
from .paths import WEB_DIR, project_version
from .version import SERVER_PRODUCT


class SayuriHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        core: SystemCore,
        cognitive: CognitiveCore,
        modules: ModuleRuntime,
        shutdown_token: str = "",
    ):
        self.core = core
        self.cognitive = cognitive
        self.modules = modules
        self.shutdown_token = shutdown_token
        super().__init__(server_address, SayuriHandler)


class SayuriHandler(BaseHTTPRequestHandler):
    server_version = SERVER_PRODUCT

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
        cognitive = self.app_server.cognitive
        modules = self.app_server.modules

        if path == "/api/health":
            status = core.status()
            overall = status["health"]["overall"]
            cognitive_status = cognitive.status()
            modules_health = modules.health()
            healthy = (
                overall == "healthy"
                and cognitive_status["running"]
                and modules_health["overall"] != "failed"
            )
            self._json(
                {
                    "status": "ok" if healthy else "degraded",
                    "project": "Sayuri Yukishiro",
                    "version": project_version(),
                    "core_version": status["core_version"],
                    "cognitive_version": cognitive_status["version"],
                    "modules_version": modules.VERSION,
                    "modules_health": modules_health["overall"],
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

        if path == "/api/cognitive":
            self._json(cognitive.status())
            return

        if path == "/api/cognitive/sessions":
            self._json({"sessions": cognitive.list_sessions()})
            return

        if path == "/api/modules":
            self._json({"modules": core.db.list_modules()})
            return

        if path == "/api/modules/runtime":
            self._json(modules.status())
            return

        if path == "/api/modules/health":
            self._json(modules.health())
            return

        if path == "/api/modules/states":
            self._json({"states": core.db.list_module_states()})
            return

        if path == "/api/system":
            core_status = core.status(deep=True)
            cognitive_status = cognitive.status()
            modules_health = modules.health()
            self._json(
                {
                    "project": "Sayuri Yukishiro",
                    "version": project_version(),
                    "core_version": core_status["core_version"],
                    "core_health": core_status["health"]["overall"],
                    "cognitive_version": cognitive_status["version"],
                    "cognitive_running": cognitive_status["running"],
                    "cognitive_sessions": cognitive_status["sessions"],
                    "database": str(core.db.path),
                    "database_check": core_status["database_check"],
                    "module_count": len(core.db.list_modules()),
                    "modules_version": modules.VERSION,
                    "modules_running": modules_health["running_count"],
                    "modules_health": modules_health["overall"],
                    "recoverable_tasks": core_status["recoverable_tasks"],
                }
            )
            return

        relative = "index.html" if path == "/" else path.lstrip("/")
        self._serve_file(relative)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/shutdown":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            self._json({"status": "forbidden"}, HTTPStatus.FORBIDDEN)
            return

        expected = self.app_server.shutdown_token
        supplied = self.headers.get("X-Sayuri-Shutdown-Token", "")
        if not expected:
            self._json({"status": "disabled"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if not supplied or not secrets.compare_digest(supplied, expected):
            self._json({"status": "forbidden"}, HTTPStatus.FORBIDDEN)
            return

        self._json({"status": "shutting_down"}, HTTPStatus.OK)
        Thread(
            target=self.app_server.shutdown,
            name="sayuri-shutdown",
            daemon=True,
        ).start()

    def log_message(self, format: str, *args) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    core = SystemCore()
    cognitive: CognitiveCore | None = None
    modules: ModuleRuntime | None = None
    server: SayuriHTTPServer | None = None
    try:
        core.start()
        cognitive = CognitiveCore(core.api, core.db)
        cognitive.start()
        modules = ModuleRuntime(
            core.api,
            core.db,
            capabilities=cognitive.capabilities,
            strict_startup=bool(core.config.get("modules.strict_startup", False)),
        )
        modules.start()
        server = SayuriHTTPServer(
            (host, port),
            core,
            cognitive,
            modules,
            shutdown_token=os.environ.get("SAYURI_SHUTDOWN_TOKEN", ""),
        )
        modules_health = modules.health()
        print(
            f"Sayuri Yukishiro {project_version()} / system core {core.CORE_VERSION} / "
            f"cognitive core {cognitive.VERSION} / module runtime {modules.VERSION} "
            f"({modules_health['running_count']}/{modules_health['module_count']} modules) "
            f"listening on http://{host}:{port}"
        )
        server.serve_forever(poll_interval=0.5)
    finally:
        if server is not None:
            server.server_close()
        if modules is not None:
            modules.stop()
        if cognitive is not None:
            cognitive.stop()
        core.stop()
