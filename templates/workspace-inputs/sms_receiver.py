from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sms_ingest import ingest_payload, now_iso


ROOT = Path(__file__).resolve().parents[1]
BAD_REQUEST_LOG = ROOT / "ledger" / "sms" / "logs" / "bad-requests.jsonl"


def parse_payload(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            return json.loads(raw, strict=False)
        except json.JSONDecodeError:
            parsed = parse_qs(raw, keep_blank_values=True)
            if parsed:
                return {key: values[-1] if values else "" for key, values in parsed.items()}
    return {"source": "android_tasker_raw", "body": raw}


def log_bad_request(raw: str, error: Exception) -> None:
    BAD_REQUEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "at": now_iso(),
        "error": type(error).__name__,
        "message": str(error),
        "raw": raw[:4000],
    }
    with BAD_REQUEST_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


class SMSHandler(BaseHTTPRequestHandler):
    server_version = "AgentRouterSmsReceiver/0.1"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path.rstrip("/") == "/health":
            self._send_json(200, {"ok": True, "time": now_iso()})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path.rstrip("/") != "/sms":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = parse_payload(raw)
            event = ingest_payload(payload)
        except Exception as exc:  # keep phone automation response compact
            log_bad_request(raw, exc)
            self._send_json(400, {"ok": False, "error": type(exc).__name__, "message": str(exc)})
            return

        self._send_json(
            200,
            {
                "ok": True,
                "id": event["id"],
                "category": event["category"],
                "action_needed": event["action_needed"],
                "task_path": event.get("task_path", ""),
            },
        )

    def log_message(self, format: str, *args) -> None:
        print(f"[{now_iso()}] {self.address_string()} {format % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local workspace SMS HTTP receiver.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), SMSHandler)
    print(f"Agent Router SMS receiver listening on http://{args.host}:{args.port}/sms")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
