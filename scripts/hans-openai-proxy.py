#!/usr/bin/env python3
"""Tiny host-side OpenAI proxy for adb-reverse MP01 BYOK tests.

The phone connects to http://127.0.0.1:<port>/v1/... through adb reverse.
This process forwards the request to https://api.openai.com without logging
authorization headers or request bodies.
"""

from __future__ import annotations

import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from typing import Iterable


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class OpenAiProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    target_host = "api.openai.com"

    def do_GET(self) -> None:
        if self.path == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "Only /healthz and OpenAI POST endpoints are supported")

    def do_POST(self) -> None:
        if not self.path.startswith("/v1/"):
            self.send_error(404, "Only /v1 OpenAI endpoints are supported")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(411, "Content-Length required")
            return
        body = self.rfile.read(length)
        headers = self._forward_headers()
        conn = http.client.HTTPSConnection(self.target_host, 443, timeout=120)
        try:
            conn.request("POST", self.path, body=body, headers=headers)
            response = conn.getresponse()
            response_body = response.read()
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                lname = name.lower()
                if lname in HOP_BY_HOP_HEADERS or lname == "content-length":
                    continue
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except Exception as exc:  # noqa: BLE001 - command-line diagnostic only.
            self.send_error(502, f"OpenAI proxy error: {exc}")
        finally:
            conn.close()

    def _forward_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Host": self.target_host}
        for name, value in self.headers.items():
            lname = name.lower()
            if lname in HOP_BY_HOP_HEADERS or lname in {"host", "content-length"}:
                continue
            headers[name] = value
        return headers

    def log_message(self, fmt: str, *args: Iterable[object]) -> None:
        sys.stderr.write("openai-proxy: " + (fmt % args) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), OpenAiProxyHandler)
    print(f"OpenAI proxy listening on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
