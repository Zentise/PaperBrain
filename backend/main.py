"""
main.py — PaperBrain FastAPI server (v2.0).

Run from backend/ directory:
    uvicorn main:app --reload --port 8000 --host 0.0.0.0
"""

import json
import os
import tempfile
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import config
import ingest as ing
import rag_chain as rag

app = FastAPI(title="PaperBrain", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class UrlRequest(BaseModel):
    url: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    model_id: str = config.DEFAULT_MODEL_ID


# ── Health / meta ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    sources = ing.get_all_sources()
    return {
        "status":    "ok",
        "version":   "2.0.0",
        "documents": len(sources),
        "models":    len(config.MODELS),
    }


@app.get("/api/models")
def get_models():
    return config.MODELS


# ── Ingestion ─────────────────────────────────────────────────────────────────

@app.post("/api/ingest/upload")
async def upload(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are allowed.")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "File too large. Max 50 MB.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = ing.ingest(tmp_path)
        result["filename"] = file.filename
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post("/api/ingest/url")
async def ingest_url(req: UrlRequest):
    try:
        result = ing.ingest(req.url)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Documents ─────────────────────────────────────────────────────────────────

@app.get("/api/documents")
def list_docs():
    return ing.get_all_sources()


@app.delete("/api/documents/{source_name:path}")
def delete_doc(source_name: str):
    ing.delete_source(source_name)
    return {"ok": True}


# ── Chat — non-streaming ──────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        result = rag.ask(req.session_id, req.message, req.model_id)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Chat — streaming (SSE) ────────────────────────────────────────────────────

@app.get("/api/chat/stream")
async def chat_stream(
    session_id: str,
    message: str,
    model_id: str = config.DEFAULT_MODEL_ID,
):
    async def generator():
        try:
            async for chunk in rag.stream_ask(session_id, message, model_id):
                yield {"data": json.dumps(chunk)}
        except Exception as e:
            yield {"data": json.dumps({"error": str(e)})}

    return EventSourceResponse(generator())


# ── Sessions ──────────────────────────────────────────────────────────────────

@app.get("/api/session/new")
def new_session():
    return {"session_id": str(uuid.uuid4())}


@app.delete("/api/session/{session_id}")
def clear_session(session_id: str):
    rag.clear_session(session_id)
    return {"ok": True}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
