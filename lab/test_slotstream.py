"""Check the adapter's HTTP behavior without loading a model."""
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


spec = importlib.util.spec_from_file_location("slotstream_serve", Path(__file__).resolve().parents[1] / "registry/launches/slotstream-serve.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.release = threading.Event()
        owner = self

        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data":[{"id":"qwen3.8-flash-next:4bit"}]}')

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append(data)
                self.send_response(400 if data.get("bad") else 200)
                self.send_header("Content-Type", "text/event-stream" if data.get("stream") else "application/json")
                self.end_headers()
                if data.get("stream"):
                    self.wfile.write(b'data: {"choices":[{"delta":{"reasoning_content":"First"}}]}\n\n')
                    self.wfile.flush()
                    owner.release.wait(5)
                    self.wfile.write(b'data: {"choices":[{"delta":{"content":"391"}}]}\n\ndata: [DONE]\n\n')
                else:
                    self.wfile.write(json.dumps(data).encode())

        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        self.encoded = []

        def encode(text, add_special_tokens):
            self.encoded.append((text, add_special_tokens))
            return SimpleNamespace(ids=[11, 22] if text else [])

        handler = adapter.handler_for(SimpleNamespace(encode=encode), self.backend.server_port)
        handler.log_message = lambda *_: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        for server in (self.backend, self.server):
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            self.addCleanup(thread.join)
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.addCleanup(self.release.set)

    def request(self, path, data=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        self.addCleanup(conn.close)
        conn.request("GET" if data is None else "POST", path, None if data is None else json.dumps(data))
        response = conn.getresponse()
        return response.status, json.loads(response.read())

    def test_reasoning_defaults_preserve_explicit_choices_and_limits(self):
        for options, expected in [({}, "medium"), ({"think": None}, "medium"), ({"think": False}, None),
                                  ({"reasoning_effort": "none"}, "none"), ({"reasoning_effort": "high"}, "high")]:
            body = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1700, **options}
            status, returned = self.request("/v1/chat/completions", body)
            self.assertEqual(status, 200)
            self.assertEqual(returned.get("reasoning_effort"), expected)
            self.assertEqual(returned.get("think"), options.get("think"))
            self.assertEqual(returned["max_tokens"], 1700)
            self.assertEqual(returned["messages"], body["messages"])

    def test_counts_actual_ids_without_chat_template(self):
        status, data = self.request("/v1/token/encode", {"text": "hola 🌍"})
        self.assertEqual((status, data), (200, {"tokens": [11, 22], "length": 2}))
        self.assertEqual(self.encoded, [("hola 🌍", False)])
        self.assertEqual(self.request("/v1/token/encode", {"text": ""})[1]["length"], 0)
        self.assertEqual(self.request("/v1/token/encode", {"text": 4})[0], 400)

    def test_stream_arrives_before_upstream_finishes(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        self.addCleanup(conn.close)
        conn.request("POST", "/v1/chat/completions", json.dumps({"stream": True}))
        response = conn.getresponse()
        self.assertEqual(response.readline(), b'data: {"choices":[{"delta":{"reasoning_content":"First"}}]}\n')
        self.release.set()
        self.assertEqual(response.read(), b'\ndata: {"choices":[{"delta":{"content":"391"}}]}\n\ndata: [DONE]\n\n')

    def test_models_errors_and_unknown_routes(self):
        self.assertEqual(self.request("/v1/models")[1]["data"][0]["id"], "qwen3.8-flash-next:4bit")
        self.assertEqual(self.request("/v1/chat/completions", {"bad": True})[0], 400)
        self.assertEqual(self.request("/unknown")[0], 404)
        self.assertEqual(self.request("/v1/chat/completions", [1])[0], 400)

    def test_artifact_change_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture"
            path.write_bytes(b"original")
            digest = hashlib.sha256(b"original").hexdigest()
            adapter.verify(path, digest)
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                adapter.verify(path, digest)


if __name__ == "__main__":
    unittest.main()
