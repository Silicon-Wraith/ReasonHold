"""Configuration for docs-rag indexing and MCP server."""

import os
from pathlib import Path

# Project root (one level up from docs-rag/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYNC_DOC_PATH = PROJECT_ROOT / "sync-doc.yaml"

# Weaviate-Docs connection
WEAVIATE_HOST = os.getenv("DOCS_RAG_WEAVIATE_HOST", "localhost")
WEAVIATE_PORT = int(os.getenv("DOCS_RAG_WEAVIATE_PORT", "8081"))
WEAVIATE_GRPC_PORT = int(os.getenv("DOCS_RAG_WEAVIATE_GRPC_PORT", "50052"))

# Ollama connection. This service is an external prerequisite.
OLLAMA_HOST = os.getenv("DOCS_RAG_OLLAMA_HOST", "localhost")
OLLAMA_PORT = int(os.getenv("DOCS_RAG_OLLAMA_PORT", "11434"))

# Embedding backend configuration. Dimensions must match the configured model.
EMBEDDING_MODEL = os.getenv("DOCS_RAG_EMBEDDING_MODEL", "qwen3-embedding:4b")
EMBEDDING_DIMS = int(os.getenv("DOCS_RAG_EMBEDDING_DIMS", "2560"))
EMBEDDING_BATCH_SIZE = int(os.getenv("DOCS_RAG_EMBEDDING_BATCH_SIZE", "8"))
EMBEDDING_CHAR_BUDGET = int(os.getenv("DOCS_RAG_EMBEDDING_CHAR_BUDGET", "12000"))
EXCLUDED_PATH_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "site-packages",
    "node_modules",
    ".ruff_cache",
    "htmlcov",
}

# Weaviate collection name (project-specific to avoid collisions)
COLLECTION_NAME = "AriadneDoc"

# Decision store
DECISIONS_FILE = Path(__file__).resolve().parent / "decisions.jsonl"
