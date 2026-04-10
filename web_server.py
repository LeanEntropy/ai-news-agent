"""Simple web server for the review page with feedback API and digest archive."""

import html
import json
import logging
import sqlite3
import threading
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

from config import settings

logger = logging.getLogger(__name__)

DATA_DIR = settings.DATA_DIR


class FeedbackHandler(SimpleHTTPRequestHandler):
    """Serves static files from data/, handles feedback POSTs, and serves digest archive."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DATA_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/digests" or self.path == "/digests/":
            self._serve_digest_index()
            return
        if self.path.startswith("/digests/"):
            try:
                digest_id = int(self.path.rsplit("/", 1)[-1])
                self._serve_digest_page(digest_id)
                return
            except ValueError:
                self.send_response(404)
                self.end_headers()
                return
        super().do_GET()

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

    # --- Digest archive ---

    def _serve_html(self, html_text: str):
        encoded = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_digest_index(self):
        conn = sqlite3.connect(str(settings.DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, period, sent_at, article_ids FROM digest_archives ORDER BY sent_at DESC LIMIT 100"
        ).fetchall()
        conn.close()

        items_html = []
        for row in rows:
            try:
                article_count = len(json.loads(row["article_ids"]))
            except Exception:
                article_count = 0
            sent_at = _format_date(row["sent_at"])
            period = html.escape(row["period"])
            items_html.append(
                f'<li><a href="/digests/{row["id"]}">{sent_at} &mdash; {period} digest</a> '
                f'<span class="count">({article_count} items)</span></li>'
            )

        body = "\n".join(items_html) or "<li>No digests yet.</li>"
        self._serve_html(_render_index_page(body))

    def _serve_digest_page(self, digest_id: int):
        conn = sqlite3.connect(str(settings.DB_PATH))
        conn.row_factory = sqlite3.Row
        digest = conn.execute(
            "SELECT id, period, sent_at, article_ids FROM digest_archives WHERE id = ?",
            (digest_id,),
        ).fetchone()

        if not digest:
            conn.close()
            self.send_response(404)
            self.end_headers()
            return

        try:
            article_ids = json.loads(digest["article_ids"])
        except Exception:
            article_ids = []

        if not article_ids:
            conn.close()
            self._serve_html(_render_digest_page(digest, []))
            return

        placeholders = ",".join("?" * len(article_ids))
        # Filter out articles marked not_for_me
        articles = conn.execute(
            f"""SELECT a.id, a.title, a.url, a.summary, a.source_name, a.category, a.final_score
                FROM articles a
                WHERE a.id IN ({placeholders})
                  AND a.id NOT IN (
                      SELECT article_id FROM feedback WHERE reaction = 'not_for_me'
                  )
                ORDER BY a.final_score DESC""",
            article_ids,
        ).fetchall()
        conn.close()

        self._serve_html(_render_digest_page(digest, [dict(a) for a in articles]))


def _format_date(iso_ts: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_ts)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_ts


def _render_index_page(list_body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Digest Archive</title>
<style>
{_CSS}
</style>
</head>
<body>
<header>
  <h1>Digest Archive</h1>
  <p class="subtitle">Past digests, with items you marked as not relevant hidden.</p>
</header>
<main>
  <ul class="digest-list">
    {list_body}
  </ul>
</main>
</body>
</html>"""


def _render_digest_page(digest: sqlite3.Row, articles: list[dict]) -> str:
    period = html.escape(digest["period"])
    sent_at = _format_date(digest["sent_at"])

    if articles:
        # Group by category
        by_cat: dict[str, list[dict]] = {}
        for a in articles:
            by_cat.setdefault(a.get("category") or "general_ai", []).append(a)

        sections = []
        for cat, items in by_cat.items():
            cat_label = html.escape(cat.replace("_", " ").title())
            cards = []
            for a in items:
                title = html.escape(a.get("title") or "Untitled")
                url = html.escape(a.get("url") or "#")
                source = html.escape(a.get("source_name") or "")
                summary = html.escape(a.get("summary") or "")
                score = a.get("final_score") or 0
                cards.append(
                    f'''<article class="card">
  <h3><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
  <p class="meta">{source} &middot; score {score:.1f}</p>
  <p class="summary">{summary}</p>
</article>'''
                )
            sections.append(
                f'<section class="category"><h2>{cat_label}</h2>{"".join(cards)}</section>'
            )
        body = "\n".join(sections)
    else:
        body = '<p class="empty">No items to show (all were marked not relevant or removed).</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{period} digest &mdash; {sent_at}</title>
<style>
{_CSS}
</style>
</head>
<body>
<header>
  <h1>{period.title()} digest</h1>
  <p class="subtitle">{sent_at}</p>
  <p><a href="/digests">&larr; back to archive</a></p>
</header>
<main>
  {body}
</main>
</body>
</html>"""


_CSS = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  max-width: 760px;
  margin: 0 auto;
  padding: 2rem 1.5rem 4rem;
  color: #1a1a1a;
  background: #fafafa;
  line-height: 1.5;
}
header { margin-bottom: 2rem; }
header h1 { margin: 0 0 0.25rem; font-size: 1.75rem; }
.subtitle { color: #666; margin: 0 0 0.5rem; }
header a { color: #0366d6; text-decoration: none; }
.digest-list { list-style: none; padding: 0; }
.digest-list li {
  padding: 0.75rem 0;
  border-bottom: 1px solid #eaeaea;
}
.digest-list a {
  color: #0366d6;
  text-decoration: none;
  font-weight: 500;
}
.digest-list a:hover { text-decoration: underline; }
.count { color: #888; font-size: 0.9rem; margin-left: 0.25rem; }
.category { margin: 2rem 0; }
.category h2 {
  font-size: 1.1rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #555;
  border-bottom: 2px solid #eaeaea;
  padding-bottom: 0.5rem;
}
.card {
  background: #fff;
  border: 1px solid #eaeaea;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin: 0.75rem 0;
}
.card h3 { margin: 0 0 0.25rem; font-size: 1.05rem; }
.card h3 a { color: #1a1a1a; text-decoration: none; }
.card h3 a:hover { color: #0366d6; }
.meta { color: #888; font-size: 0.85rem; margin: 0 0 0.5rem; }
.summary { margin: 0; color: #444; }
.empty { color: #888; font-style: italic; }
"""


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
    logger.info(f"Digest archive at http://localhost:{port}/digests")
    return server
