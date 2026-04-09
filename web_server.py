"""Simple web server for the review page with feedback API."""

import asyncio
import json
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import threading
import sqlite3

from config import settings

logger = logging.getLogger(__name__)

DATA_DIR = settings.DATA_DIR


class FeedbackHandler(SimpleHTTPRequestHandler):
    """Serves static files from data/ and handles feedback POST requests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DATA_DIR), **kwargs)

    def do_POST(self):
        if self.path == "/api/feedback":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                article_id = data.get("article_id")
                reaction = data.get("reaction")
                if article_id and reaction in ("relevant", "not_for_me"):
                    _store_feedback(int(article_id), reaction)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True}).encode())
                else:
                    self.send_response(400)
                    self.end_headers()
            except Exception as e:
                logger.error(f"Feedback error: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logs


def _store_feedback(article_id: int, reaction: str):
    """Store feedback directly in SQLite (sync, since http.server is sync)."""
    from datetime import datetime, timezone
    conn = sqlite3.connect(str(settings.DB_PATH))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO feedback (article_id, reaction, timestamp) VALUES (?, ?, ?)",
        (article_id, reaction, now),
    )
    conn.commit()
    conn.close()


def start_web_server(port: int = 8080):
    """Start the web server in a background thread."""
    server = HTTPServer(("0.0.0.0", port), FeedbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Web review page running at http://localhost:{port}")
    return server
