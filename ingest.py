"""
ingest.py — Document ingestion pipeline for AskMyDocs.

Accepts a PDF file path, HTTP URL, or YouTube URL.
Loads, chunks, embeds, and stores documents in ChromaDB.
"""

import os
import re
import sys
import time

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader, YoutubeLoader
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_ollama import OllamaEmbeddings

load_dotenv()
_gemini_key = os.getenv("GEMINI")
if _gemini_key:
    os.environ["GOOGLE_API_KEY"] = _gemini_key

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def detect_source_type(source: str) -> str:
    """Return 'youtube', 'url', or 'pdf' based on the input string."""
    if re.match(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/", source):
        return "youtube"
    if source.startswith("http://") or source.startswith("https://"):
        return "url"
    return "pdf"


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


def chunk_documents(docs, chunk_size=800, chunk_overlap=80):
    """Split documents into chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(docs)
    print(f"   Split into {len(chunks)} chunk(s)")
    return chunks


def get_embeddings():
    """Return the configured embedding model.

    Set EMBEDDING_PROVIDER=ollama in .env to use a local Ollama model
    (no rate limits). Requires `ollama pull nomic-embed-text` first.
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
    if provider == "ollama":
        model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        return OllamaEmbeddings(model=model)
    emb = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")
    return emb


def store_chunks(chunks):
    """Embed chunks and add to ChromaDB in batches to stay within rate limits."""
    embeddings = get_embeddings()
    BATCH_SIZE = 100  # paid tier allows higher throughput
    MAX_RETRIES = 5

    if os.path.exists(CHROMA_DIR):
        print("📦 Appending to existing ChromaDB …")
        db = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    else:
        print("📦 Creating new ChromaDB …")
        db = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)

    total = len(chunks)
    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"   Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks) …")

        for attempt in range(MAX_RETRIES):
            try:
                db.add_documents(batch)
                break
            except Exception as e:
                if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                    wait = min(60, 10 * (attempt + 1))  # 10s, 20s, 30s … 60s
                    print(f"   ⏳ Rate limited, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES}) …")
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError(f"Failed to embed batch {batch_num} after {MAX_RETRIES} retries")

        # Small pause to avoid burst spikes on the paid tier
        if i + BATCH_SIZE < total:
            time.sleep(1)

    print(f"✅ Stored {total} chunk(s) in ChromaDB at {CHROMA_DIR}")
    return db


def ingest(source: str):
    """Full ingestion pipeline: detect → load → chunk → store."""
    source_type = detect_source_type(source)
    print(f"\n🔍 Detected source type: {source_type}")
    docs = load_documents(source, source_type)
    chunks = chunk_documents(docs)
    store_chunks(chunks)
    print("🎉 Ingestion complete!\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <pdf_path | url | youtube_url>")
        sys.exit(1)
    ingest(sys.argv[1])
