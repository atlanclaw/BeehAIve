"""Configuration from environment variables."""

import os


class Config:
    """Application configuration loaded from environment."""

    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "pkb_documents")

    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "localhost")
    OLLAMA_PORT: int = int(os.getenv("OLLAMA_PORT", "11434"))
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "384"))

    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    CLOUD_FALLBACK_MODEL: str = os.getenv(
        "CLOUD_FALLBACK_MODEL", "meta-llama/llama-3.3-70b:free"
    )

    ENABLE_TOON: bool = os.getenv("ENABLE_TOON", "false").lower() == "true"

    DATA_DIR: str = os.getenv("DATA_DIR", "/app/data/documents")

    TOP_K: int = int(os.getenv("TOP_K", "5"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

    # Obsidian Integration
    OBSIDIAN_VAULT_PATH: str = os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian-vault")
    OBSIDIAN_SYNC_INTERVAL: int = int(os.getenv("OBSIDIAN_SYNC_INTERVAL", "30"))
    PKB_API_URL: str = os.getenv("PKB_API_URL", "http://localhost:8000")
    BACKLOG_PATH: str = os.getenv("BACKLOG_PATH", "/app/backlog")


config = Config()
