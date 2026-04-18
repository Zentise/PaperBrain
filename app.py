"""
app.py — Streamlit UI for AskMyDocs.

Upload PDFs, paste URLs or YouTube links, and chat with your documents.
"""

import os
import tempfile

import streamlit as st
from dotenv import load_dotenv

from ingest import ingest
from rag_chain import ask, build_chain, load_vectorstore

load_dotenv()

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="AskMyDocs", page_icon="📚", layout="wide")

# ── Session state defaults ───────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chain" not in st.session_state:
    st.session_state.chain = None
if "db" not in st.session_state:
    st.session_state.db = None
if "provider" not in st.session_state:
    st.session_state.provider = "gemini"
if "ingested_files" not in st.session_state:
    st.session_state.ingested_files = set()
if "ingested_urls" not in st.session_state:
    st.session_state.ingested_urls = set()

# ── Auto-load chain on startup if chroma_db exists ──────────────────────────
if st.session_state.chain is None and os.path.exists(CHROMA_DIR):
    try:
        chain, db = build_chain(st.session_state.provider)
        st.session_state.chain = chain
        st.session_state.db = db
    except Exception:
        pass

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    # LLM provider toggle
    provider = st.radio(
        "LLM Provider",
        ["gemini", "groq"],
        index=0 if st.session_state.provider == "gemini" else 1,
        format_func=lambda x: "Google Gemini 2.0 Flash" if x == "gemini" else "Groq Llama 3.3 70B",
    )
    if provider != st.session_state.provider:
        st.session_state.provider = provider
        st.session_state.chain = None
        st.session_state.db = None
        st.rerun()

    st.divider()

    # PDF upload
    st.subheader("📄 Upload PDFs")
    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type=["pdf"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        for uploaded in uploaded_files:
            file_key = f"{uploaded.name}_{uploaded.size}"
            if file_key in st.session_state.ingested_files:
                continue
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name
            try:
                with st.spinner(f"Ingesting {uploaded.name} …"):
                    ingest(tmp_path)
                st.session_state.ingested_files.add(file_key)
                st.success(f"✅ {uploaded.name} ingested")
            except Exception as e:
                st.error(f"❌ {uploaded.name}: {e}")
            finally:
                os.unlink(tmp_path)

    st.divider()

    # URL / YouTube input
    st.subheader("🔗 URL or YouTube Link")
    url_input = st.text_input("Paste a URL or YouTube link")
    if st.button("Ingest URL") and url_input:
        try:
            with st.spinner("Ingesting …"):
                ingest(url_input)
            st.success("✅ URL ingested")
        except Exception as e:
            st.error(f"❌ {e}")

    st.divider()

    # Load / Reload chain
    if st.button("🔄 Load / Reload Chain"):
        try:
            with st.spinner("Building chain …"):
                chain, db = build_chain(st.session_state.provider)
            st.session_state.chain = chain
            st.session_state.db = db
            st.success("✅ Chain loaded")
        except FileNotFoundError as e:
            st.warning(str(e))
        except Exception as e:
            st.error(f"❌ {e}")

    # Clear chat history
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        if st.session_state.chain and hasattr(st.session_state.chain, "memory"):
            st.session_state.chain.memory.clear()
        st.rerun()

# ── Main chat area ───────────────────────────────────────────────────────────
st.title("📚 AskMyDocs")
st.caption("Upload documents and chat with them using RAG + LangChain")

# Render full chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Show metadata for assistant messages
        if msg["role"] == "assistant" and "confidence" in msg:
            confidence = msg["confidence"]
            if confidence >= 80:
                badge = f"🟢 Confidence: {confidence}%"
            elif confidence >= 55:
                badge = f"🟡 Confidence: {confidence}%"
            else:
                badge = f"🔴 Confidence: {confidence}%"
            st.caption(badge)

            if msg.get("sources"):
                source_badges = []
                for s in msg["sources"]:
                    if s["type"] == "pdf":
                        source_badges.append(f"📄 {s['label']} (p.{s['page']})")
                    elif s["type"] == "youtube":
                        source_badges.append(f"▶️ {s['label']}")
                    elif s["type"] == "url":
                        source_badges.append(f"🔗 {s['url']}")
                st.caption("Sources: " + " · ".join(source_badges))

# Chat input
if prompt := st.chat_input("Ask a question about your documents …"):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Check chain is loaded
    if st.session_state.chain is None:
        warning_msg = "⚠️ Chain not loaded. Please ingest documents and click **Load / Reload Chain** in the sidebar."
        st.session_state.messages.append({"role": "assistant", "content": warning_msg})
        with st.chat_message("assistant"):
            st.warning(warning_msg)
    else:
        with st.chat_message("assistant"):
            with st.spinner("Thinking …"):
                result = ask(
                    st.session_state.chain,
                    st.session_state.db,
                    prompt,
                )

            st.markdown(result["answer"])

            confidence = result["confidence"]
            if confidence >= 80:
                badge = f"🟢 Confidence: {confidence}%"
            elif confidence >= 55:
                badge = f"🟡 Confidence: {confidence}%"
            else:
                badge = f"🔴 Confidence: {confidence}%"
            st.caption(badge)

            if result["sources"]:
                source_badges = []
                for s in result["sources"]:
                    if s["type"] == "pdf":
                        source_badges.append(f"📄 {s['label']} (p.{s['page']})")
                    elif s["type"] == "youtube":
                        source_badges.append(f"▶️ {s['label']}")
                    elif s["type"] == "url":
                        source_badges.append(f"🔗 {s['url']}")
                st.caption("Sources: " + " · ".join(source_badges))

        st.session_state.messages.append({
            "role": "assistant",
            "content": result["answer"],
            "confidence": confidence,
            "sources": result["sources"],
        })
