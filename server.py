"""Local HTTP prototype: serves the website, chat, and a direct solver preview."""

# --- Standard-library imports and backend dependencies ---
import argparse
import getpass
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from openai import OpenAIError

from gate_assistant import GateAssistant
from gate_solver import optimize_gates

# --- Server-wide session state and static asset allowlist ---
WEB = Path(__file__).resolve().parent / "web"
SESSIONS = {}
SESSION_LOCK = threading.Lock()
WORK_LOCK = threading.Lock()
ASSETS = {
    "/": ("planner.html", "text/html; charset=utf-8"),
    "/planner.js": ("planner.js", "text/javascript; charset=utf-8"),
    "/planner.css": ("planner.css", "text/css; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    # --- Add restrictive headers and serialize the selected response type ---
    def send(self, status, value, content_type="application/json; charset=utf-8"):
        body = json.dumps(value).encode() if content_type.startswith("application/json") else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    # --- Serve only explicit website assets and safe config metadata ---
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/config":
            return self.send(200, {"chat_available": bool(os.getenv("OPENAI_API_KEY"))})
        if path in ASSETS:
            filename, mime = ASSETS[path]
            return self.send(200, (WEB / filename).read_bytes(), mime)
        self.send(404, {"error": "Not found"})

    # --- Validate same-origin JSON requests and dispatch supported operations ---
    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in {"/api/chat", "/api/solve"}:
            return self.send(404, {"error": "Not found"})
        # Browser requests must be from this origin; no permissive CORS.
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            return self.send(403, {"error": "Cross-origin requests are not allowed"})
        if self.headers.get_content_type() != "application/json":
            return self.send(415, {"error": "Use application/json"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16000:
                return self.send(413, {"error": "Request must be 1-16000 bytes"})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Request must be a JSON object")
        except (ValueError, UnicodeDecodeError):
            return self.send(400, {"error": "Invalid JSON request"})
        if not WORK_LOCK.acquire(blocking=False):
            return self.send(429, {"error": "A request is running. Please try again shortly."})
        try:
            if path == "/api/solve":
                # Only expose scenario controls accepted by the shared solver API.
                supported_options = {
                    "dataset",
                    "flexible_gates",
                    "time_limit_seconds",
                    "aircraft_count",
                    "gate_count",
                    "lock_percentage",
                    "wing_to_wing_connections",
                    "ground_handling_minutes_per_passenger",
                    "ground_handling_overrides",
                }
                if set(data) - supported_options:
                    raise ValueError("Unsupported solver option")
                result = optimize_gates(**data)
                return self.send(200, {"results": [result]})
            message = data.get("message")
            if not isinstance(message, str) or not message.strip() or len(message) > 4000:
                raise ValueError("Message must be 1-4000 characters")
            if not os.getenv("OPENAI_API_KEY"):
                return self.send(503, {"error": "Set OPENAI_API_KEY on the server to enable chat. You can still run a solver preview."})
            session_id = data.get("session_id")
            if session_id is not None and not isinstance(session_id, str):
                raise ValueError("Invalid session ID")
            now = time.monotonic()
            with SESSION_LOCK:
                for key in list(SESSIONS):
                    if now - SESSIONS[key][1] > 3600:
                        del SESSIONS[key]
                if session_id is None:
                    if len(SESSIONS) >= 100:
                        return self.send(503, {"error": "Session capacity reached. Try again later."})
                    session_id = str(uuid.uuid4())
                    SESSIONS[session_id] = [GateAssistant(), now]
                if session_id not in SESSIONS:
                    return self.send(410, {"error": "Conversation expired. Start a new conversation."})
                assistant = SESSIONS[session_id][0]
                SESSIONS[session_id][1] = now
            answer = assistant.ask(message)
            self.send(200, {"session_id": session_id, "answer": answer, "results": assistant.last_results})
        except ValueError as exc:
            self.send(400, {"error": str(exc)})
        except OpenAIError:
            self.send(502, {"error": "OpenAI request failed. Check the server's API key, model access, and connection."})
        except Exception:
            self.log_error("Backend request failed")
            self.send(500, {"error": "The backend could not finish this request. Please retry."})
        finally:
            WORK_LOCK.release()


# --- Command-line configuration and local HTTP server lifecycle ---
def main():
    parser = argparse.ArgumentParser(description="Gate Logic HTTP prototype")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")))
    parser.add_argument("--prompt-key", action="store_true",
                        help="Ask for a hidden API key at startup, even if one is already configured")
    args = parser.parse_args()
    if args.prompt_key or (not os.getenv("OPENAI_API_KEY") and sys.stdin.isatty()):
        try:
            key = getpass.getpass("OpenAI API key (hidden; Enter for solver preview only): ").strip()
        except (EOFError, KeyboardInterrupt):
            parser.exit(1, "\nStartup cancelled.\n")
        # This updates only this process; nothing is saved to a file or shell profile.
        os.environ["OPENAI_API_KEY"] = key
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Gate Logic: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
