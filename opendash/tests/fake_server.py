"""A throwaway HTTP server that mimics the opencode serve API.

Raw socket-based to avoid Python HTTPServer threading issues.
"""
from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs


class FakeServer:
    """A minimal HTTP server in a thread, on a free port."""

    def __init__(self, agents=None, permissions=None, questions=None,
                 session_id="ses_fake0000000001"):
        self._agents = agents if agents is not None else [
            {"name": "default"}, {"name": "build"}]
        self._permissions = permissions or []
        self._questions = questions or {}
        self._session_id = session_id
        self.created_sessions = []
        self.prompted = []
        self.aborted = []
        self.patched = []
        self.deleted = []

        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)
        self._sock.close()

    def write_server_json(self, state: Path, pid: int = 1):
        (state / "server.json").write_text(json.dumps(
            {"url": self.url, "port": self.port, "pid": pid, "started": 1}))

    def _loop(self):
        self._sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self._handle(conn)
            except Exception:
                pass
            finally:
                conn.close()

    def _handle(self, conn):
        conn.settimeout(2)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                return
            data += chunk

        header, _, rest = data.partition(b"\r\n\r\n")
        lines = header.decode().split("\r\n")
        request_line = lines[0]
        method, path, _ = request_line.split(" ", 2)
        parsed = urlparse(path)
        clean_path = parsed.path.rstrip("/")

        content_length = 0
        for line in lines[1:]:
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())

        body_data = rest
        while len(body_data) < content_length:
            chunk = conn.recv(4096)
            if not chunk:
                break
            body_data += chunk

        body = None
        if content_length and body_data:
            try:
                body = json.loads(body_data[:content_length])
            except json.JSONDecodeError:
                body = None

        code, response_body = self._route(method, clean_path, parsed, body)
        self._send(conn, code, response_body)

    def _route(self, method, path, parsed, body):
        if method == "GET" and path == "/session":
            return 200, []
        if method == "GET" and path == "/agent":
            return 200, self._agents
        if method == "GET" and path.startswith("/permission"):
            return 200, self._permissions
        if method == "GET" and "/question" in path:
            parts = path.split("/")
            sid = parts[3] if len(parts) > 3 else ""
            q = self._questions.get(sid)
            return 200, {"data": q} if q else {"data": None}
        if method == "POST" and path == "/session":
            self.created_sessions.append(body)
            return 200, {"id": self._session_id}
        if method == "POST" and "/prompt_async" in path:
            self.prompted.append((path, body))
            return 204, None
        if method == "POST" and "/abort" in path:
            self.aborted.append(path)
            return 200, None
        if method == "PATCH" and path.startswith("/session/"):
            self.patched.append((path, body))
            return 200, None
        if method == "DELETE" and path.startswith("/session/"):
            self.deleted.append(path)
            return 200, None
        return 404, None

    def _send(self, conn, code, body):
        if body is None:
            conn.sendall(f"HTTP/1.1 {code}\r\ncontent-length: 0\r\n\r\n".encode())
        else:
            payload = json.dumps(body).encode()
            conn.sendall(
                f"HTTP/1.1 {code}\r\ncontent-type: application/json\r\n"
                f"content-length: {len(payload)}\r\n\r\n".encode() + payload)