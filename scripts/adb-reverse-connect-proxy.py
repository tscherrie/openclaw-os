#!/usr/bin/env python3
"""Small HTTP CONNECT proxy for Android tests over adb reverse.

The proxy is intentionally narrow: by default it only allows CONNECT tunnels to
api.openai.com:443. It does not inspect TLS traffic and never logs request
payloads or secrets.
"""

from __future__ import annotations

import argparse
import selectors
import socket
import socketserver
import sys
from typing import Iterable


class ConnectProxy(socketserver.StreamRequestHandler):
    timeout = 30

    def handle(self) -> None:
        try:
            request_line = self.rfile.readline(8192).decode("iso-8859-1").strip()
            if not request_line:
                return
            method, target, _version = request_line.split(" ", 2)
            while True:
                line = self.rfile.readline(8192)
                if line in (b"\r\n", b"\n", b""):
                    break
            if method.upper() != "CONNECT":
                self.reject(405, "CONNECT only")
                return
            host, port = self.parse_target(target)
            allowed_hosts = self.server.allowed_hosts  # type: ignore[attr-defined]
            allowed_ports = self.server.allowed_ports  # type: ignore[attr-defined]
            if host not in allowed_hosts or port not in allowed_ports:
                self.reject(403, "target not allowed")
                return
            with socket.create_connection((host, port), timeout=self.timeout) as upstream:
                self.log(f"CONNECT {host}:{port}")
                self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.wfile.flush()
                self.relay(self.connection, upstream)
        except Exception as exc:  # pragma: no cover - defensive runtime logging
            self.log(f"connection failed: {exc}")

    def reject(self, code: int, message: str) -> None:
        body = f"{code} {message}\n".encode("utf-8")
        self.wfile.write(
            f"HTTP/1.1 {code} {message}\r\nContent-Length: {len(body)}\r\n\r\n".encode(
                "ascii"
            )
        )
        self.wfile.write(body)
        self.wfile.flush()

    def parse_target(self, target: str) -> tuple[str, int]:
        if ":" not in target:
            raise ValueError(f"CONNECT target missing port: {target}")
        host, port_text = target.rsplit(":", 1)
        return host.lower().strip("[]"), int(port_text)

    def relay(self, client: socket.socket, upstream: socket.socket) -> None:
        client.setblocking(False)
        upstream.setblocking(False)
        selector = selectors.DefaultSelector()
        selector.register(client, selectors.EVENT_READ, upstream)
        selector.register(upstream, selectors.EVENT_READ, client)
        while True:
            events = selector.select(timeout=self.timeout)
            if not events:
                return
            for key, _mask in events:
                source = key.fileobj
                sink = key.data
                data = source.recv(65536)
                if not data:
                    return
                sink.sendall(data)

    def log(self, message: str) -> None:
        remote = f"{self.client_address[0]}:{self.client_address[1]}"
        print(f"{remote} {message}", file=sys.stderr, flush=True)


class ThreadingConnectProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        allowed_hosts: Iterable[str],
        allowed_ports: Iterable[int],
    ) -> None:
        self.allowed_hosts = {host.lower() for host in allowed_hosts}
        self.allowed_ports = set(allowed_ports)
        super().__init__(server_address, ConnectProxy)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--allow-host", action="append", default=["api.openai.com"])
    parser.add_argument("--allow-port", action="append", type=int, default=[443])
    args = parser.parse_args()

    with ThreadingConnectProxy(
        (args.listen, args.port),
        args.allow_host,
        args.allow_port,
    ) as server:
        print(
            f"listening on {args.listen}:{args.port}; allowed hosts={','.join(server.allowed_hosts)}",
            file=sys.stderr,
            flush=True,
        )
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
