"""Authenticated, local-only Make.com intake webhook.

It queues validated requests as JSON; it does NOT execute shell commands or publish
content. Keep bound to 127.0.0.1 unless deployed behind HTTPS and a trusted gateway.
Set MAKE_WEBHOOK_API_KEY in the environment before starting.
"""
from __future__ import annotations
import hmac
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "make_queue"
MAX_BODY = 64 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

class Handler(BaseHTTPRequestHandler):
    server_version = "ArabicMediaIntake/1.0"

    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlparse(self.path).path != "/v1/jobs":
            return self.reply(404, {"error": "not_found"})
        expected = os.environ.get("MAKE_WEBHOOK_API_KEY", "")
        supplied = self.headers.get("x-make-apikey", "")
        if len(expected) < 32 or not hmac.compare_digest(supplied, expected):
            return self.reply(401, {"error": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > MAX_BODY:
                return self.reply(413, {"error": "invalid_body_size"})
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
        except Exception:
            return self.reply(400, {"error": "invalid_json"})
        request_id = data.get("request_id", "")
        channel = data.get("channel", "")
        topic = data.get("topic", "")
        if not isinstance(request_id, str) or not ID_RE.fullmatch(request_id):
            return self.reply(422, {"error": "request_id must be 8-128 safe characters"})
        if channel not in {"children", "public"}:
            return self.reply(422, {"error": "channel must be children or public"})
        if not isinstance(topic, str) or not topic.strip() or len(topic) > 500:
            return self.reply(422, {"error": "topic must be 1-500 characters"})
        QUEUE.mkdir(parents=True, exist_ok=True)
        target = QUEUE / (request_id + ".json")
        if target.exists():
            return self.reply(200, {"status": "duplicate_ignored", "request_id": request_id})
        item = {"request_id": request_id, "channel": channel, "topic": topic.strip(),
                "received_at_unix": int(time.time()), "status": "queued"}
        # Exclusive creation prevents concurrent duplicate IDs from overwriting jobs.
        try:
            with target.open("x", encoding="utf-8") as handle:
                json.dump(item, handle, ensure_ascii=False, indent=2)
        except FileExistsError:
            return self.reply(200, {"status": "duplicate_ignored", "request_id": request_id})
        return self.reply(202, {"status": "queued_for_review", "request_id": request_id})

    def log_message(self, fmt, *args):
        # Avoid logging headers, tokens, or request bodies.
        print("make_webhook:", fmt % args)

def main():
    key = os.environ.get("MAKE_WEBHOOK_API_KEY", "")
    if len(key) < 32:
        raise SystemExit("Set MAKE_WEBHOOK_API_KEY to a random secret of at least 32 characters.")
    host = os.environ.get("MAKE_WEBHOOK_HOST", "127.0.0.1")
    port = int(os.environ.get("MAKE_WEBHOOK_PORT", "8787"))
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Refusing non-loopback bind. Use a hardened HTTPS reverse proxy for remote Make access.")
    print(f"Authenticated Make intake listening on {host}:{port}; requests are queued, not published.")
    HTTPServer((host, port), Handler).serve_forever()

if __name__ == "__main__":
    main()
