"""
ingest.py — Document ingestion pipeline for PaperBrain.

Accepts a PDF file path, HTTP URL, or YouTube URL.
Loads, chunks, embeds, and stores documents in ChromaDB.
"""

import os
import re
import sys
import time

import config
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader, YoutubeLoader
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_ollama import OllamaEmbeddings

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
if config.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = config.GEMINI_API_KEY

CHROMA_DIR = config.CHROMA_PATH


# ── Source detection ──────────────────────────────────────────────────────────

def detect_source_type(source: str) -> str:
    """Return 'youtube', 'url', or 'pdf' based on the input string."""
    if re.match(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/", source):
        return "youtube"
    if source.startswith("http://") or source.startswith("https://"):
        return "url"
    return "pdf"


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_documents(source: str, source_type: str):
    """Load documents from the given source and tag with metadata."""
    if source_type == "pdf":
        if not os.path.isfile(source):
            raise FileNotFoundError(f"PDF not found: {source}")
        print(f"📄 Loading PDF: {source}")
        loader = PyMuPDFLoader(source)
        docs = loader.load()
        file_name = os.path.basename(source)
        for doc in docs:
            doc.metadata["source_type"] = "pdf"
            doc.metadata["file_name"] = file_name
            doc.metadata["page"] = doc.metadata.get("page", 0)

    elif source_type == "youtube":
        print(f"▶️  Loading YouTube transcript: {source}")
        try:
            loader = YoutubeLoader.from_youtube_url(source, add_video_info=True)
            docs = loader.load()
        except Exception as e:
            print(f"   ⚠️ YoutubeLoader failed ({e}), trying direct transcript fetch …")
            from youtube_transcript_api import YouTubeTranscriptApi
            from langchain_core.documents import Document
            video_id = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", source)
            if not video_id:
                raise ValueError(f"Could not extract video ID from: {source}")
            video_id = video_id.group(1)
            ytt = YouTubeTranscriptApi()
            transcript = ytt.fetch(video_id)
            text = " ".join(snippet.text for snippet in transcript)
            docs = [Document(page_content=text, metadata={"source": source})]
        for doc in docs:
            doc.metadata["source_type"] = "youtube"
            doc.metadata["url"] = source
            doc.metadata["page"] = 0

    elif source_type == "url":
        print(f"🔗 Loading web page: {source}")
        loader = WebBaseLoader(source)
        docs = loader.load()
        for doc in docs:
            doc.metadata["source_type"] = "url"
            doc.metadata["url"] = source
            doc.metadata["page"] = 0

    else:
        raise ValueError(f"Unknown source type: {source_type}")

    print(f"   Loaded {len(docs)} document(s)")
    return docs


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_documents(docs, chunk_size=None, chunk_overlap=None):
    """Split documents into chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or config.CHUNK_SIZE,
        chunk_overlap=chunk_overlap or config.CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)
    print(f"   Split into {len(chunks)} chunk(s)")
    return chunks


# ── Embeddings ────────────────────────────────────────────────────────────────

def get_embeddings():
    """Return the configured embedding model.

    Set EMBEDDING_PROVIDER=ollama in .env to use a local Ollama model
    (no rate limits). Requires `ollama pull nomic-embed-text` first.
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
    if provider == "ollama":
        model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        return OllamaEmbeddings(model=model)
    return GoogleGenerativeAIEmbeddings(model=config.EMBEDDING_MODEL)


# ── Storage ───────────────────────────────────────────────────────────────────

def store_chunks(chunks):
    """Embed chunks and add to ChromaDB in batches to stay within rate limits."""
    embeddings = get_embeddings()
    batch_size = config.BATCH_SIZE
    max_retries = 5

    if os.path.exists(CHROMA_DIR):
        print("📦 Appending to existing ChromaDB …")
    else:
        print("📦 Creating new ChromaDB …")
    db = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)

    total = len(chunks)
    for i in range(0, total, batch_size):
        batch = chunks[i: i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        print(f"   Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks) …")

        for attempt in range(max_retries):
            try:
                db.add_documents(batch)
                break
            except Exception as e:
                if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                    wait = min(60, 10 * (attempt + 1))
                    print(f"   ⏳ Rate limited, waiting {wait}s (attempt {attempt + 1}/{max_retries}) …")
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError(f"Failed to embed batch {batch_num} after {max_retries} retries")

        if i + batch_size < total:
            time.sleep(1)

    print(f"✅ Stored {total} chunk(s) in ChromaDB at {CHROMA_DIR}")
    return db


# ── Source management ─────────────────────────────────────────────────────────

def get_all_sources() -> list[dict]:
    """Return deduplicated list of {name, source_type, chunks}."""
    if not os.path.exists(CHROMA_DIR):
        return []
    try:
        db = Chroma(persist_directory=CHROMA_DIR, embedding_function=get_embeddings())
        results = db._collection.get(include=["metadatas"])
        source_map: dict[str, dict] = {}
        for meta in results.get("metadatas") or []:
            source_type = meta.get("source_type", "unknown")
            name = meta.get("file_name") if source_type == "pdf" else meta.get("url", "unknown")
            if not name:
                name = "unknown"
            if name not in source_map:
                source_map[name] = {"name": name, "source_type": source_type, "chunks": 0}
            source_map[name]["chunks"] += 1
        return list(source_map.values())
    except Exception as exc:
        print(f"⚠️ get_all_sources error: {exc}")
        return []


def delete_source(name: str) -> None:
    """Delete all ChromaDB documents matching file_name or url metadata."""
    if not os.path.exists(CHROMA_DIR):
        return
    db = Chroma(persist_directory=CHROMA_DIR, embedding_function=get_embeddings())
    results = db._collection.get(include=["metadatas"])
    ids_to_delete = [
        results["ids"][i]
        for i, meta in enumerate(results.get("metadatas") or [])
        if meta.get("file_name") == name or meta.get("url") == name
    ]
    if ids_to_delete:
        db._collection.delete(ids=ids_to_delete)
        print(f"🗑️  Deleted {len(ids_to_delete)} chunk(s) for: {name}")
    else:
        print(f"⚠️ No chunks found for: {name}")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def ingest(source: str) -> dict:
    """Full ingestion pipeline: detect → load → chunk → store.

    Returns {"chunks": N, "source_type": type}
    """
    source_type = detect_source_type(source)
    print(f"\n🔍 Detected source type: {source_type}")
    docs = load_documents(source, source_type)
    chunks = chunk_documents(docs)
    store_chunks(chunks)
    print("🎉 Ingestion complete!\n")
    return {"chunks": len(chunks), "source_type": source_type}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <pdf_path | url | youtube_url>")
        sys.exit(1)
    ingest(sys.argv[1])
