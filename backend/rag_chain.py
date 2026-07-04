"""
rag_chain.py — Conversational RAG chain for PaperBrain.

LLM: OpenRouter (via langchain-openai ChatOpenAI).
Embeddings: Google gemini-embedding-001 (unchanged).
Vector store: ChromaDB (unchanged).
"""

import os
import asyncio
from threading import Lock

import config
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_openai import ChatOpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
if config.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GEMINI_API_KEY

CHROMA_DIR = config.CHROMA_PATH

_SYSTEM_PROMPT = (
    "You are a document assistant. Answer using ONLY the context below. "
    "If the context lacks the answer, say \"I don't have enough information.\""
    " Cite source (file+page for PDFs, URL/title otherwise) at the end.\n\n"
    "Context:\n{context}"
)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "{question}"),
    ]
)

# ── Session store ─────────────────────────────────────────────────────────────
# _sessions: session_id -> {chat_history: [(q, a), ...], db: Chroma|None, model_id: str|None}
_sessions: dict = {}
_lock = Lock()


def _get_session(session_id: str) -> dict:
    with _lock:
        if session_id not in _sessions:
            _sessions[session_id] = {
                "chat_history": [],
                "db": None,
                "model_id": None,
            }
        return _sessions[session_id]


# ── Embeddings ────────────────────────────────────────────────────────────────

def get_embeddings():
    provider = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
    if provider == "ollama":
        model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        return OllamaEmbeddings(model=model)
    return GoogleGenerativeAIEmbeddings(model=config.EMBEDDING_MODEL)


# ── Vector store ──────────────────────────────────────────────────────────────

def load_vectorstore() -> Chroma:
    if not os.path.exists(CHROMA_DIR):
        raise FileNotFoundError(
            f"ChromaDB directory not found at {CHROMA_DIR}. "
            "Ingest documents first with ingest.py."
        )
    return Chroma(persist_directory=CHROMA_DIR, embedding_function=get_embeddings())


# ── LLM ───────────────────────────────────────────────────────────────────────

def get_llm(model_id: str, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_id,
        openai_api_key=config.OPENROUTER_API_KEY,
        openai_api_base=config.OPENROUTER_BASE,
        temperature=config.TEMPERATURE,
        max_tokens=1024,
        streaming=streaming,
        default_headers={
            "HTTP-Referer": config.APP_URL,
            "X-Title": config.APP_NAME,
        },
    )


# ── Confidence ────────────────────────────────────────────────────────────────

def get_confidence(db: Chroma, query: str) -> float:
    results = db.similarity_search_with_relevance_scores(query, k=1)
    if not results:
        return 0.0
    _doc, score = results[0]
    return round(score * 100, 1)


# ── Source helpers ────────────────────────────────────────────────────────────

def _build_source_entry(meta: dict) -> dict:
    source_type = meta.get("source_type", "unknown")
    entry: dict = {"type": source_type}
    if source_type == "pdf":
        entry["label"] = meta.get("file_name", "unknown")
        entry["page"]  = meta.get("page", 0)
        entry["url"]   = ""
    elif source_type == "youtube":
        entry["label"] = meta.get("title", meta.get("url", "YouTube"))
        entry["page"]  = 0
        entry["url"]   = meta.get("url", "")
    elif source_type == "url":
        entry["label"] = meta.get("url", "Web")
        entry["page"]  = 0
        entry["url"]   = meta.get("url", "")
    else:
        entry["label"] = "Unknown"
        entry["page"]  = 0
        entry["url"]   = ""
    return entry


def _dedup_sources(sources: list[dict]) -> list[dict]:
    seen: set = set()
    deduped: list[dict] = []
    for s in sources:
        key = (s["type"], s["label"] if s["type"] == "pdf" else s["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped


# ── Context / retriever helpers ───────────────────────────────────────────────

def _ensure_db(state: dict) -> Chroma:
    if state["db"] is None:
        state["db"] = load_vectorstore()
    return state["db"]


def _get_retriever(db: Chroma):
    return db.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": config.TOP_K, "score_threshold": config.SCORE_THRESHOLD},
    )


def _build_history_messages(chat_history: list) -> list:
    msgs = []
    for human, ai in chat_history[-config.MAX_HISTORY_TURNS:]:
        msgs.append(HumanMessage(content=human))
        msgs.append(AIMessage(content=ai))
    return msgs


# ── Public API: non-streaming ask ─────────────────────────────────────────────

def ask(session_id: str, question: str, model_id: str) -> dict:
    """Return {answer, sources, confidence, provider}."""
    state = _get_session(session_id)

    with _lock:
        db = _ensure_db(state)

    retriever = _get_retriever(db)
    docs = retriever.invoke(question)
    context = "\n\n".join(doc.page_content for doc in docs)

    history_messages = _build_history_messages(state["chat_history"])
    messages = _PROMPT.format_messages(
        context=context,
        question=question,
        chat_history=history_messages,
    )

    llm = get_llm(model_id, streaming=False)
    response = llm.invoke(messages)
    answer = response.content

    with _lock:
        state["chat_history"].append((question, answer))
        state["model_id"] = model_id

    sources = _dedup_sources([_build_source_entry(doc.metadata) for doc in docs])
    confidence = get_confidence(db, question)

    return {
        "answer":     answer,
        "sources":    sources,
        "confidence": confidence,
        "provider":   model_id,
    }


# ── Public API: streaming ask ─────────────────────────────────────────────────

async def stream_ask(session_id: str, question: str, model_id: str):
    """Async generator yielding {token:str} chunks, then a final {done:True, ...}."""
    state = _get_session(session_id)

    # Load DB (blocking — run in thread to avoid blocking event loop)
    loop = asyncio.get_event_loop()
    with _lock:
        if state["db"] is None:
            state["db"] = await loop.run_in_executor(None, load_vectorstore)
    db = state["db"]

    # Retrieve docs in executor
    retriever = _get_retriever(db)
    docs = await loop.run_in_executor(None, retriever.invoke, question)
    context = "\n\n".join(doc.page_content for doc in docs)

    history_messages = _build_history_messages(state["chat_history"])
    messages = _PROMPT.format_messages(
        context=context,
        question=question,
        chat_history=history_messages,
    )

    streaming_llm = get_llm(model_id, streaming=True)
    full_answer = ""

    async for chunk in streaming_llm.astream(messages):
        token = chunk.content or ""
        if token:
            full_answer += token
            yield {"token": token}

    # Persist history
    with _lock:
        state["chat_history"].append((question, full_answer))
        state["model_id"] = model_id

    # Confidence in executor
    confidence = await loop.run_in_executor(None, get_confidence, db, question)
    sources = _dedup_sources([_build_source_entry(doc.metadata) for doc in docs])

    yield {
        "done":       True,
        "confidence": confidence,
        "sources":    sources,
        "provider":   model_id,
    }


# ── Session control ───────────────────────────────────────────────────────────

def clear_session(session_id: str) -> None:
    with _lock:
        _sessions.pop(session_id, None)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading knowledge base …")
    db = load_vectorstore()
    print(f"Ready! Using model: {config.DEFAULT_MODEL_ID}\nType 'quit' to exit.\n")

    chat_history: list = []
    while True:
        q = input("You: ").strip()
        if q.lower() in ("quit", "exit", "q"):
            break
        if not q:
            continue

        session = "cli-session"
        result = ask(session, q, config.DEFAULT_MODEL_ID)
        print(f"\n{result['answer']}")
        print(f"   Confidence: {result['confidence']}%")
        if result["sources"]:
            for s in result["sources"]:
                if s["type"] == "pdf":
                    print(f"     PDF: {s['label']} (page {s['page']})")
                elif s["type"] == "youtube":
                    print(f"     YouTube: {s['label']}")
                else:
                    print(f"     Web: {s['url']}")
        print()
