"""
app.py — PaperBrain Flask server

Serves the dashboard at / and exposes JSON endpoints for the SPA.
"""

import os
import tempfile
from threading import Lock
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from werkzeug.utils import secure_filename

from ingest import ingest
from rag_chain import ask, build_chain

load_dotenv()
if (k := os.getenv("GEMINI")):
    os.environ["GOOGLE_API_KEY"] = k

BASE   = os.path.dirname(__file__)
DB_DIR = os.path.join(BASE, "chroma_db")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "paperbrain-dev-change-me")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

PROVIDERS = {
    "gemini": "Gemini 2.5 Flash",
    "groq":   "Llama 3.3 70B",
}

_sessions: dict = {}
_lock = Lock()


# ── helpers ───────────────────────────────────────────────────────────────────

def _has_db() -> bool:
    return os.path.isfile(os.path.join(DB_DIR, "chroma.sqlite3"))


def _get_state() -> dict:
    sid = session.setdefault("sid", uuid4().hex)
    with _lock:
        return _sessions.setdefault(sid, {
            "chain": None, "db": None, "provider": "gemini",
            "messages": [], "sources": [],
        })


def _chunk_count(s: dict) -> int:
    try:
        return s["db"]._collection.count()
    except Exception:
        return 0


def _serialize(s: dict) -> dict:
    return {
        "ready":         s["chain"] is not None and s["db"] is not None,
        "hasDocuments":  _has_db(),
        "provider":      s["provider"],
        "providerLabel": PROVIDERS.get(s["provider"], s["provider"]),
        "chunkCount":    _chunk_count(s),
        "messageCount":  len(s["messages"]),
        "sources":       s["sources"],
        "messages":      s["messages"],
    }


def _rebuild(s: dict) -> None:
    """Tear down and rebuild the RAG chain. No-ops if no DB exists."""
    s["chain"] = None
    s["db"] = None
    if _has_db():
        chain, db = build_chain(s["provider"])
        s["chain"] = chain
        s["db"] = db


def _err(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": msg}), code


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def api_status():
    s = _get_state()
    # Auto-load on first visit if a DB already exists
    if _has_db() and s["chain"] is None:
        try:
            _rebuild(s)
        except Exception:
            pass
    return jsonify(_serialize(s))


@app.post("/api/reload")
def api_reload():
    s = _get_state()
    if not _has_db():
        return _err("No documents indexed yet. Add sources first.")
    try:
        _rebuild(s)
        s["messages"] = []
        return jsonify({"ok": True, "status": _serialize(s)})
    except Exception as e:
        return _err(str(e), 500)


@app.post("/api/provider")
def api_provider():
    data = request.get_json(silent=True) or {}
    prov = data.get("provider", "gemini")
    if prov not in PROVIDERS:
        return _err("Invalid provider.")
    s = _get_state()
    s["provider"] = prov
    s["messages"] = []
    if _has_db():
        try:
            _rebuild(s)
        except Exception:
            pass
    return jsonify({"ok": True, "status": _serialize(s)})


@app.post("/api/upload")
def api_upload():
    files = request.files.getlist("files")
    if not files:
        return _err("No files provided.")
    s = _get_state()
    ingested = []
    for f in files:
        name = secure_filename(f.filename or "")
        if not name.lower().endswith(".pdf"):
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            f.save(tmp)
            path = tmp.name
        try:
            ingest(path)
            s["sources"].append({"type": "pdf", "name": name, "url": ""})
            ingested.append(name)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    if not ingested:
        return _err("No valid PDF files found.")
    s["messages"] = []
    _rebuild(s)
    return jsonify({"ok": True, "ingested": ingested, "status": _serialize(s)})


@app.post("/api/ingest-url")
def api_ingest_url():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return _err("No URL provided.")
    s = _get_state()
    try:
        ingest(url)
    except Exception as e:
        return _err(str(e), 500)
    is_yt = "youtube.com" in url or "youtu.be" in url
    s["sources"].append({
        "type": "youtube" if is_yt else "url",
        "name": url,
        "url":  url,
    })
    s["messages"] = []
    _rebuild(s)
    return jsonify({"ok": True, "status": _serialize(s)})


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    q = (data.get("message") or "").strip()
    if not q:
        return _err("Message is empty.")
    s = _get_state()
    if not _has_db():
        return _err("No documents indexed. Add sources first.")
    if s["chain"] is None:
        try:
            _rebuild(s)
        except Exception as e:
            return _err(str(e), 500)
    s["messages"].append({"role": "user", "content": q})
    try:
        result = ask(s["chain"], s["db"], q)
    except Exception as e:
        s["messages"].pop()
        return _err(str(e), 500)
    msg = {
        "role":       "assistant",
        "content":    result["answer"],
        "confidence": result["confidence"],
        "sources":    result["sources"],
    }
    s["messages"].append(msg)
    return jsonify({"ok": True, "message": msg, "status": _serialize(s)})


@app.post("/api/clear")
def api_clear():
    s = _get_state()
    s["messages"] = []
    if s["chain"]:
        try:
            s["chain"].memory.clear()
        except Exception:
            pass
    return jsonify({"ok": True, "status": _serialize(s)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
