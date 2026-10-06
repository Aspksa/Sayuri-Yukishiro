from __future__ import annotations

import json
import mimetypes
import os
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse

from .cognitive.engine import CognitiveCore
from .core.runtime import SystemCore
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
        shutdown_token: str = "",
    ):
        self.core = core
        self.cognitive = cognitive
        self.shutdown_token = shutdown_token
        self.control_token = secrets.token_urlsafe(32)
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

    def _is_loopback(self) -> bool:
        return self.client_address[0] in {"127.0.0.1", "::1"}

    def _host_is_loopback(self) -> bool:
        raw = self.headers.get("Host", "").strip().lower()
        if not raw:
            return False
        if raw.startswith("["):
            closing = raw.find("]")
            host = raw[: closing + 1] if closing >= 0 else raw
        else:
            host = raw.split(":", 1)[0]
        return host in {"127.0.0.1", "localhost", "[::1]"}

    def _local_shell_allowed(self) -> bool:
        return self._is_loopback() and self._host_is_loopback()

    def _control_allowed(self) -> bool:
        if not self._local_shell_allowed():
            return False
        supplied = self.headers.get("X-Sayuri-Control-Token", "")
        expected = self.app_server.control_token
        return bool(
            supplied
            and expected
            and secrets.compare_digest(supplied, expected)
        )

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
        if not self._local_shell_allowed():
            self._json({"status": "forbidden"}, HTTPStatus.FORBIDDEN)
            return

        path = urlparse(self.path).path
        core = self.app_server.core
        cognitive = self.app_server.cognitive

        if path == "/api/health":
            status = core.status()
            overall = status["health"]["overall"]
            cognitive_status = cognitive.status()
            healthy = overall == "healthy" and cognitive_status["running"]
            self._json(
                {
                    "status": "ok" if healthy else "degraded",
                    "project": "Sayuri Yukishiro",
                    "version": project_version(),
                    "core_version": status["core_version"],
                    "cognitive_version": cognitive_status["version"],
                    "pid": os.getpid(),
                }
            )
            return

        if path == "/api/session/control-token":
            if not self._local_shell_allowed():
                self._json(
                    {"status": "forbidden"},
                    HTTPStatus.FORBIDDEN,
                )
                return
            self._json({"token": self.app_server.control_token})
            return

        if path == "/api/update/status":
            if not self._local_shell_allowed():
                self._json(
                    {"status": "forbidden"},
                    HTTPStatus.FORBIDDEN,
                )
                return
            self._json(core.update.status())
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

        if path == "/api/system":
            core_status = core.status(deep=True)
            cognitive_status = cognitive.status()
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
                    "recoverable_tasks": core_status["recoverable_tasks"],
                    "update": core_status["update"],
                }
            )
            return

        relative = "index.html" if path == "/" else path.lstrip("/")
        self._serve_file(relative)

    def do_POST(self) -> None:
        if not self._local_shell_allowed():
            self._json({"status": "forbidden"}, HTTPStatus.FORBIDDEN)
            return

        path = urlparse(self.path).path
        core = self.app_server.core

        if path == "/api/update/check":
            if not self._control_allowed():
                self._json(
                    {"status": "forbidden"},
                    HTTPStatus.FORBIDDEN,
                )
                return
            try:
                job_id = core.update.request_check()
            except RuntimeError as exc:
                self._json(
                    {"status": "busy", "message": str(exc)},
                    HTTPStatus.CONFLICT,
                )
                return
            self._json(
                {
                    "status": "accepted",
                    "job_id": job_id,
                    "update": core.update.status(),
                },
                HTTPStatus.ACCEPTED,
            )
            return

        if path == "/api/update/apply":
            if not self._control_allowed():
                self._json(
                    {"status": "forbidden"},
                    HTTPStatus.FORBIDDEN,
                )
                return
            try:
                update_status = core.update.prepare_apply()
            except RuntimeError as exc:
                self._json(
                    {"status": "blocked", "message": str(exc)},
                    HTTPStatus.CONFLICT,
                )
                return

            self._json(
                {
                    "status": "accepted",
                    "update": update_status,
                    "message": (
                        "Sayuri will stop gracefully; the update helper "
                        "will apply and verify the update."
                    ),
                },
                HTTPStatus.ACCEPTED,
            )

            def shutdown_after_response() -> None:
                time.sleep(0.25)
                self.app_server.shutdown()

            Thread(
                target=shutdown_after_response,
                name="sayuri-update-shutdown",
                daemon=True,
            ).start()
            return

        if path == "/api/shutdown":
            if not self._local_shell_allowed():
                self._json(
                    {"status": "forbidden"},
                    HTTPStatus.FORBIDDEN,
                )
                return

            expected = self.app_server.shutdown_token
            supplied = self.headers.get("X-Sayuri-Shutdown-Token", "")
            if not expected:
                self._json(
                    {"status": "disabled"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            if not supplied or not secrets.compare_digest(supplied, expected):
                self._json(
                    {"status": "forbidden"},
                    HTTPStatus.FORBIDDEN,
                )
                return

            self._json({"status": "shutting_down"}, HTTPStatus.OK)
            Thread(
                target=self.app_server.shutdown,
                name="sayuri-shutdown",
                daemon=True,
            ).start()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    core = SystemCore(port=port)
    cognitive: CognitiveCore | None = None
    server: SayuriHTTPServer | None = None
    try:
        core.start()
        cognitive = CognitiveCore(core.api, core.db)
        cognitive.start()
        server = SayuriHTTPServer(
            (host, port),
            core,
            cognitive,
            shutdown_token=os.environ.get("SAYURI_SHUTDOWN_TOKEN", ""),
        )
        print(
            f"Sayuri Yukishiro {project_version()} / system core "
            f"{core.CORE_VERSION} / cognitive core {cognitive.VERSION} "
            f"listening on http://{host}:{port}"
        )
        server.serve_forever(poll_interval=0.5)
    finally:
        if server is not None:
            server.server_close()
        if cognitive is not None:
            cognitive.stop()
        core.stop()
