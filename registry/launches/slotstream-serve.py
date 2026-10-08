"""Run Slotstream 0.2.28 with medium reasoning and the lab's tokenizer endpoint.

The native server handles inference, templates, tools and streaming. This adapter
only supplies the reasoning default when the client omits it and counts raw text
with the checkpoint's tokenizer. It does not change replies or generation limits.
This release's bundled Metal library requires macOS 26.
"""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HASHES = {
    "slotstream": "fee022e64b37abd25260d2c5552fda4d9a66383c86e68449d814dd284c94d9e0",
    "mlx.metallib": "dc59d1cceb1a5c7e578232e6e41e28e2c73c9463ac6dbc3886c3ee17ffc270ed",
    "tokenizer.json": "0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3",
    "lookahead/tap-correction-attention-rank128-v1.safetensors": "37b00d3a32d1e1889a1794bbb8e97905a157a77c0508db620c1a11f2a895f7f5",
}
MAX_BODY = 4 * 1024 * 1024


def verify(path, expected):
    with path.open("rb") as f:
        actual = hashlib.file_digest(f, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"checksum mismatch: {path}")


def handler_for(tokenizer, backend_port):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != "/v1/models":
                self.reply(404, {"error": "unknown endpoint"})
                return
            self.forward()

        def do_POST(self):
            if self.path not in ("/v1/token/encode", "/v1/chat/completions"):
                self.reply(404, {"error": "unknown endpoint"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    self.reply(413, {"error": "body must be between 1 byte and 4 MiB"})
                    return
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("body must be an object")
                if self.path == "/v1/token/encode":
                    if not isinstance(data.get("text"), str):
                        raise ValueError("text must be a string")
                    ids = tokenizer.encode(data["text"], add_special_tokens=False).ids
                    self.reply(200, {"tokens": ids, "length": len(ids)})
                    return
                if data.get("think") is None and data.get("reasoning_effort") is None:
                    data["reasoning_effort"] = "medium"
            except (ValueError, UnicodeError) as e:
                self.reply(400, {"error": str(e)})
                return
            self.forward(json.dumps(data).encode())

        def forward(self, body=None):
            conn = http.client.HTTPConnection("127.0.0.1", backend_port, timeout=3600)
            started = False
            try:
                conn.request(self.command, self.path, body, {"Content-Type": "application/json"})
                response = conn.getresponse()
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                self.end_headers()
                started = True
                if "text/event-stream" in response.getheader("Content-Type", ""):
                    for line in response:
                        self.wfile.write(line)
                        self.wfile.flush()
                else:
                    self.wfile.write(response.read())
            except (OSError, http.client.HTTPException) as e:
                if not started:
                    self.reply(502, {"error": str(e)})
                # Closing the upstream connection also cancels a disconnected client.
            finally:
                conn.close()
                self.close_connection = True

    return Handler


def main():
    from tokenizers import Tokenizer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="./slotstream")
    parser.add_argument("--model", required=True)
    parser.add_argument("--memory-gb", type=float, required=True)
    parser.add_argument("--max-context", type=int, required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend-port", type=int, default=11435)
    args = parser.parse_args()
    binary, model = Path(args.binary).resolve(), Path(args.model).resolve()
    verify(binary, HASHES["slotstream"])
    verify(binary.with_name("mlx.metallib"), HASHES["mlx.metallib"])
    verify(model / "tokenizer.json", HASHES["tokenizer.json"])
    correction = "lookahead/tap-correction-attention-rank128-v1.safetensors"
    verify(model / correction, HASHES[correction])
    tokenizer = Tokenizer.from_file(str(model / "tokenizer.json"))
    # Refuse occupied ports before starting a model, rather than testing an old server.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.backend_port))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(tokenizer, args.backend_port))
    server.timeout = 1
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    process = None
    try:
        process = subprocess.Popen([
            str(binary), "serve", "--model", str(model),
            "--memory-gb", str(args.memory_gb), "--max-context", str(args.max_context),
            "--mtp", "on", "--gpu-keepalive", "on", "--port", str(args.backend_port),
        ])
        deadline = time.monotonic() + 3600
        while not stop.is_set() and process.poll() is None:
            conn = http.client.HTTPConnection("127.0.0.1", args.backend_port, timeout=1)
            try:
                conn.request("GET", "/v1/models")
                response = conn.getresponse()
                ready = response.status == 200 and bool(json.loads(response.read()).get("data"))
                if ready:
                    break
            except (OSError, ValueError, http.client.HTTPException):
                pass
            finally:
                conn.close()
            if time.monotonic() >= deadline:
                raise TimeoutError("Slotstream did not load within an hour")
            stop.wait(1)
        if process.poll() is not None:
            raise RuntimeError(f"Slotstream exited with status {process.returncode}")
        if stop.is_set():
            return
        print(f"Slotstream ready at http://127.0.0.1:{args.port}/v1", flush=True)
        while not stop.is_set() and process.poll() is None:
            server.handle_request()
        if not stop.is_set():
            raise RuntimeError(f"Slotstream exited with status {process.returncode}")
    finally:
        server.server_close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
