"""
rag_chain.py — Conversational RAG chain for AskMyDocs.

Built with LangChain Core LCEL primitives (no deprecated langchain.chains).
"""

import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langchain_groq import ChatGroq
from langchain_ollama import OllamaEmbeddings

load_dotenv()
_gemini_key = os.getenv("GEMINI")
if _gemini_key:
    os.environ["GOOGLE_API_KEY"] = _gemini_key

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")

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


# ── Thin memory wrapper so app.py can call chain.memory.clear() ──────────────
class _Memory:
    def __init__(self, owner):
        self._owner = owner

    def clear(self):
        self._owner.chat_history.clear()


class RAGChain:
    """LCEL-based conversational RAG chain with built-in chat history."""

    def __init__(self, llm, retriever, prompt=_PROMPT):
        self._llm = llm
        self._retriever = retriever
        self._prompt = prompt
        self.chat_history = []
        self.memory = _Memory(self)

    def invoke(self, inputs):
        question = inputs["question"]

        docs = self._retriever.invoke(question)
        context = "\n\n".join(doc.page_content for doc in docs)

        history_messages = []
        for human, ai in self.chat_history[-3:]:  # keep last 3 turns to save tokens
            history_messages.append(HumanMessage(content=human))
            history_messages.append(AIMessage(content=ai))

        messages = self._prompt.format_messages(
            context=context,
            question=question,
            chat_history=history_messages,
        )
        try:
            response = self._llm.invoke(messages)
        except ChatGoogleGenerativeAIError as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                print("⚠️ Gemini rate-limited, falling back to Groq …")
                fallback = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2)
                response = fallback.invoke(messages)
            else:
                raise
        answer = response.content

        self.chat_history.append((question, answer))

        return {"answer": answer, "source_documents": docs}


# ── Public helpers ────────────────────────────────────────────────────────────

def get_embeddings():
    provider = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
    if provider == "ollama":
        model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        return OllamaEmbeddings(model=model)
    emb = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")
    return emb


def load_vectorstore():
    if not os.path.exists(CHROMA_DIR):
        raise FileNotFoundError(
            f"ChromaDB directory not found at {CHROMA_DIR}. "
            "Ingest documents first with ingest.py."
        )
    return Chroma(persist_directory=CHROMA_DIR, embedding_function=get_embeddings())


def get_llm(provider="gemini"):
    if provider == "groq":
        return ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2)
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.2, max_output_tokens=1024)


def build_chain(provider="gemini"):
    db = load_vectorstore()
    retriever = db.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 3, "score_threshold": 0.50},
    )
    chain = RAGChain(llm=get_llm(provider), retriever=retriever)
    return chain, db


def get_confidence(db, query):
    results = db.similarity_search_with_relevance_scores(query, k=1)
    if not results:
        return 0.0
    _doc, score = results[0]
    return round(score * 100, 1)


def _build_source_entry(meta):
    source_type = meta.get("source_type", "unknown")
    entry = {"type": source_type}
    if source_type == "pdf":
        entry["label"] = meta.get("file_name", "unknown")
        entry["page"] = meta.get("page", 0)
        entry["url"] = ""
    elif source_type == "youtube":
        entry["label"] = meta.get("title", meta.get("url", "YouTube"))
        entry["page"] = 0
        entry["url"] = meta.get("url", "")
    elif source_type == "url":
        entry["label"] = meta.get("url", "Web")
        entry["page"] = 0
        entry["url"] = meta.get("url", "")
    else:
        entry["label"] = "Unknown"
        entry["page"] = 0
        entry["url"] = ""
    return entry


def _dedup_sources(sources):
    seen = set()
    deduped = []
    for s in sources:
        key = (s["type"], s["label"] if s["type"] == "pdf" else s["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped


def ask(chain, db, question):
    result = chain.invoke({"question": question})
    answer = result.get("answer", "")
    source_docs = result.get("source_documents", [])

    sources = [_build_source_entry(doc.metadata) for doc in source_docs]
    sources = _dedup_sources(sources)
    confidence = get_confidence(db, question)

    return {"answer": answer, "sources": sources, "confidence": confidence}


if __name__ == "__main__":
    print("Loading chain ...")
    chain, db = build_chain("gemini")
    print("Ready! Type your questions (type 'quit' to exit).\n")

    while True:
        q = input("You: ").strip()
        if q.lower() in ("quit", "exit", "q"):
            break
        if not q:
            continue
        result = ask(chain, db, q)
        print(f"\n{result['answer']}")
        print(f"   Confidence: {result['confidence']}%")
        if result["sources"]:
            print("   Sources:")
            for s in result["sources"]:
                if s["type"] == "pdf":
                    print(f"     PDF: {s['label']} (page {s['page']})")
                elif s["type"] == "youtube":
                    print(f"     YouTube: {s['label']}")
                else:
                    print(f"     Web: {s['url']}")
        print()
