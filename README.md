# PaperBrain

**Chat with your documents.** Upload PDFs, paste web URLs or YouTube links, and ask questions — PaperBrain retrieves the most relevant passages and generates grounded answers with source citations.

![Architecture](assets/architecture.svg)

---

## Features

- **Multi-source ingestion** — PDFs, web pages, and YouTube transcripts
- **Conversational memory** — multi-turn chat with context retention (last 3 turns)
- **Source citations** — every answer cites the document, page, or URL it came from
- **Confidence scoring** — color-coded badge on every response (🟢 ≥75% · 🟡 50–74% · 🔴 <50%)
- **Dual LLM** — Google Gemini 2.5 Flash Lite (primary) or Groq Llama 3.3 70B, switchable at any time
- **Auto-fallback** — if Gemini hits a rate limit (429), the chain silently retries on Groq
- **Persistent vector store** — ChromaDB on disk; re-ingesting appends without overwriting
- **Three-panel web UI** — Sources panel · Chat · Context panel — dark-theme SPA served by Flask

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web server | Flask ≥3 |
| Orchestration | LangChain Core (LCEL) |
| LLM — primary | Google Gemini 2.5 Flash Lite (`langchain-google-genai`) |
| LLM — fallback | Groq Llama 3.3 70B (`langchain-groq`) |
| Embeddings | Google `gemini-embedding-001` (or Ollama `nomic-embed-text`) |
| Vector store | ChromaDB ≥0.5 |
| PDF loader | PyMuPDF |
| Web loader | LangChain `WebBaseLoader` (BeautifulSoup4 / lxml) |
| YouTube loader | `youtube-transcript-api` / `YoutubeLoader` |
| Frontend | Vanilla HTML + CSS + JS (no framework) |

---

## Project Structure

```
PaperBrain/
├── .env                    # API keys (not committed)
├── requirements.txt        # Python dependencies
├── app.py                  # Flask server + JSON API
├── ingest.py               # Ingestion pipeline (also usable as CLI)
├── rag_chain.py            # RAG chain, retriever, ask() helper (also usable as CLI)
├── templates/
│   └── index.html          # Three-panel SPA (Jinja2 template)
├── static/
│   ├── css/app.css         # Dark-theme stylesheet (~26 KB)
│   └── js/app.js           # SPA frontend logic (~20 KB)
├── data/                   # Drop PDFs here for CLI ingestion
└── chroma_db/              # Auto-created by ChromaDB after first ingest
```

> **Note:** The `backend/` and `frontend/` directories in the repo root are legacy scaffolding and are not used by the running application. All active code lives in the root-level files listed above.

---

## Setup

### 1. Clone & create a virtual environment

```bash
git clone https://github.com/Zentise/PaperBrain.git
cd PaperBrain

python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API keys

Create a `.env` file in the project root:

```env
GEMINI=your_gemini_api_key
GROQ=your_groq_api_key        # optional — only needed when using the Groq provider
```

- **Gemini key** — [Google AI Studio](https://aistudio.google.com/app/apikey)
- **Groq key** — [Groq Console](https://console.groq.com/keys)

---

## Running the App

```bash
python app.py
```

Then open **http://localhost:5000** in your browser.

The server auto-loads your existing ChromaDB on first request if one is already present — no manual reload needed.

Set `PORT` in `.env` to change the default port (5000).

---

## Usage

### Web UI

1. Click **+** (Add source) in the Sources panel or the **"Add your first source"** button on the welcome screen.
2. In the drawer, either drag-and-drop PDFs or paste a web / YouTube URL and click **Ingest**.
3. Once the status pill in the top bar shows **Ready**, type a question in the chat composer and press **Enter**.
4. The **Context** panel on the right shows the confidence score and cited sources for the last answer.
5. Switch between Gemini and Llama 3.3 using the model toggle in the top bar. Switching rebuilds the chain and clears chat history.

### CLI — Ingest documents

```bash
# PDF
python ingest.py path/to/document.pdf

# Web page
python ingest.py https://example.com/article

# YouTube video
python ingest.py https://www.youtube.com/watch?v=VIDEO_ID
```

### CLI — Interactive chat

```bash
python rag_chain.py
```

---

## API Reference

The Flask server exposes a JSON API consumed by the SPA:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the three-panel dashboard |
| `GET` | `/api/status` | Returns chain state, provider, chunk count, message history |
| `POST` | `/api/reload` | Rebuilds the RAG chain from the existing vector store |
| `POST` | `/api/provider` | Switches LLM provider (`{"provider": "gemini" \| "groq"}`) |
| `POST` | `/api/upload` | Uploads and ingests one or more PDF files (multipart/form-data) |
| `POST` | `/api/ingest-url` | Ingests a web page or YouTube URL (`{"url": "..."}`) |
| `POST` | `/api/chat` | Sends a message (`{"message": "..."}`) and returns the answer |
| `POST` | `/api/clear` | Clears the conversation history |

All mutation endpoints return `{ "ok": true, "status": { ... } }` on success, or `{ "ok": false, "error": "..." }` on failure.

---

## How It Works

1. **Ingest** — documents are loaded (PyMuPDF / WebBaseLoader / YoutubeLoader), split into 800-character chunks (80-character overlap), embedded with Google's `gemini-embedding-001` model, and stored in ChromaDB. Batches of 100 are written with automatic back-off on rate-limit errors.
2. **Retrieve** — at query time, the top-3 most relevant chunks with a similarity score ≥ 0.50 are fetched via `similarity_score_threshold` search.
3. **Generate** — `RAGChain` formats the retrieved context plus the last 3 turns of chat history into a prompt and calls the active LLM. If Gemini returns a 429, it silently retries on Groq Llama 3.3 70B.
4. **Score** — confidence is computed as the top-1 `similarity_search_with_relevance_scores` result × 100, and bucketed into high / medium / low bands.
5. **Display** — the SPA renders the answer in the chat panel with a confidence bar and source-citation chips, and updates the Context panel with the detailed breakdown.

### Session model

Each browser tab gets its own server-side session (Flask + `uuid4` sid). The RAG chain, vector store handle, provider choice, and message history are all stored per-session in a process-local dict protected by a `threading.Lock`.

---

## Notes

- YouTube ingestion requires the video to have captions/transcripts enabled. If `YoutubeLoader` fails, the pipeline falls back to `YouTubeTranscriptApi` directly.
- ChromaDB data persists across restarts in `./chroma_db`. Delete that directory to start fresh.
- Temperature is fixed at `0.2` on both LLMs for consistent, factual responses.
- Set `EMBEDDING_PROVIDER=ollama` in `.env` to use a local Ollama embedding model instead of Gemini (requires `ollama pull nomic-embed-text`). Useful to avoid API rate limits during bulk ingestion.
- Set `OLLAMA_EMBED_MODEL` to override the default `nomic-embed-text` Ollama model.
- Set `SECRET_KEY` in `.env` for a stable Flask session secret in production.
- The upload size limit is 50 MB per request (`MAX_CONTENT_LENGTH`). Increase it in `app.py` if needed.
