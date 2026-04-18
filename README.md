# 📚 AskMyDocs

A document chatbot powered by RAG (Retrieval-Augmented Generation) and LangChain. Upload PDFs, paste web URLs, or YouTube links — then chat with your documents in natural language.

## Features

- **Multi-source ingestion** — PDFs, web pages, and YouTube transcripts
- **Conversational memory** — multi-turn chat with context retention
- **Source citations** — every answer cites the document, page, or URL it came from
- **Confidence scoring** — color-coded confidence badge on every response (🟢 ≥80% · 🟡 55–79% · 🔴 <55%)
- **Dual LLM support** — Google Gemini 2.0 Flash (primary) or Groq Llama 3.3 70B (fallback), toggled from the sidebar
- **Persistent vector store** — ChromaDB stored on disk at `./chroma_db`; re-ingesting adds to existing data

## Architecture
![alt text](assets\architecture.svg)

## Tech Stack

| Layer | Library |
|---|---|
| Orchestration | LangChain |
| LLM (primary) | Google Gemini 2.0 Flash via `langchain-google-genai` |
| LLM (fallback) | Groq Llama 3.3 70B via `langchain-groq` |
| Embeddings | Google `models/embedding-001` |
| Vector store | ChromaDB |
| UI | Streamlit |
| Env vars | python-dotenv |

## Project Structure

```
AskMyDocs/
├── .env                  # API keys
├── requirements.txt
├── data/                 # Drop PDFs here or use the UI uploader
├── chroma_db/            # Auto-created by ChromaDB after first ingest
├── ingest.py             # Ingestion pipeline (CLI + importable)
├── rag_chain.py          # RAG chain, retriever, ask() helper (CLI + importable)
└── app.py                # Streamlit UI
```

## Setup

### 1. Clone & create a virtual environment

```bash
git clone https://github.com/your-org/AskMyDocs.git
cd AskMyDocs
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API keys

Copy `.env` and fill in your keys:

```env
GOOGLE_API_KEY=your_google_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

- **Google API key** — [Google AI Studio](https://aistudio.google.com/app/apikey)
- **Groq API key** — [Groq Console](https://console.groq.com/keys)

## Usage

### Streamlit UI (recommended)

```bash
streamlit run app.py
```

Use the sidebar to upload PDFs, paste URLs/YouTube links, switch LLM providers, and reload the chain.

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

## How It Works

1. **Ingest** — documents are loaded, split into 1000-token chunks (200 overlap), embedded with Google's embedding model, and stored in ChromaDB.
2. **Retrieve** — at query time, the top-4 most relevant chunks above a 0.70 similarity threshold are fetched.
3. **Generate** — a `ConversationalRetrievalChain` passes the retrieved context and chat history to the LLM, which is instructed to answer only from context and cite sources.
4. **Display** — the Streamlit UI renders the answer with confidence badge and source citation badges.

## Notes

- YouTube ingestion requires the video to have captions/transcripts enabled.
- ChromaDB data persists across sessions; delete `./chroma_db` to start fresh.
- Temperature is set to 0.2 for both LLMs for consistent, factual responses.
