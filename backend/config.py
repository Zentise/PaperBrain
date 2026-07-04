from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# GCP Embeddings (keep existing)
GEMINI_API_KEY  = os.getenv("GEMINI")
EMBEDDING_MODEL = "models/gemini-embedding-001"

# OpenRouter (new LLM gateway)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE    = "https://openrouter.ai/api/v1"
APP_NAME           = "PaperBrain"
APP_URL            = "https://paperbrain.app"

# ChromaDB — resolved relative to this file so it's cwd-independent
CHROMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chroma_db")

# RAG settings
TOP_K             = 3
SCORE_THRESHOLD   = 0.50
CHUNK_SIZE        = 800
CHUNK_OVERLAP     = 80
BATCH_SIZE        = 100
TEMPERATURE       = 0.2
MAX_HISTORY_TURNS = 3

MODELS = [
    {
        "id":          "google/gemini-2.5-flash-lite-preview-06-17",
        "name":        "Gemini 2.5 Flash Lite",
        "label":       "gemini",
        "tier":        "fast",
        "description": "Fast, best for quick Q&A",
        "context":     "1M",
    },
    {
        "id":          "meta-llama/llama-3.3-70b-instruct",
        "name":        "Llama 3.3 70B",
        "label":       "llama",
        "tier":        "fast",
        "description": "Open source, free tier",
        "context":     "128k",
    },
    {
        "id":          "deepseek/deepseek-chat-v3-0324",
        "name":        "DeepSeek V3",
        "label":       "deepseek",
        "tier":        "balanced",
        "description": "Best quality/cost ratio",
        "context":     "128k",
    },
    {
        "id":          "anthropic/claude-sonnet-4-5",
        "name":        "Claude Sonnet",
        "label":       "claude",
        "tier":        "balanced",
        "description": "Complex reasoning",
        "context":     "200k",
    },
    {
        "id":          "openai/gpt-4o",
        "name":        "GPT-4o",
        "label":       "gpt4o",
        "tier":        "powerful",
        "description": "Reliable, well-rounded",
        "context":     "128k",
    },
    {
        "id":          "deepseek/deepseek-r1",
        "name":        "DeepSeek R1",
        "label":       "r1",
        "tier":        "powerful",
        "description": "Shows reasoning steps",
        "context":     "128k",
    },
]

DEFAULT_MODEL_ID = MODELS[0]["id"]
