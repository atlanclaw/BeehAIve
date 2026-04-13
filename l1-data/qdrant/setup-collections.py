"""
L1 Qdrant Collections Setup.
Idempotentes Script — legt alle PKB Collections an wenn nicht vorhanden.
Kein Embedding, kein Chunking, keine Ingestion-Logik (das ist L2).

Aufruf: python3 l1-data/qdrant/setup-collections.py
Pflicht-Env: QDRANT_URL (default: http://localhost:6333)
             EMBEDDING_DIM (default: 768)
"""
import os
import sys
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PayloadSchemaType,
    HnswConfigDiff,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("pkb.setup_collections")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

# HNSW-Parameter (advisory aus LH hardware-profile.yaml)
HNSW_M = int(os.getenv("QDRANT_HNSW_M", "16"))
HNSW_EF_CONSTRUCT = int(os.getenv("QDRANT_HNSW_EF_CONSTRUCT", "100"))

COLLECTIONS: dict[str, dict] = {
    "pkb_vault": {
        "description": "Vault-Notizen (Markdown-Chunks)",
        "payload_indexes": {
            "docid":       PayloadSchemaType.KEYWORD,
            "path":        PayloadSchemaType.KEYWORD,
            "title":       PayloadSchemaType.TEXT,
            "status":      PayloadSchemaType.KEYWORD,
            "topics":      PayloadSchemaType.KEYWORD,
            "categories":  PayloadSchemaType.KEYWORD,
            "chunk_index": PayloadSchemaType.INTEGER,
            "created_at":  PayloadSchemaType.DATETIME,
            "updated_at":  PayloadSchemaType.DATETIME,
        },
    },
    "pkb_memory": {
        "description": "Verdichtete Memory-Inhalte (MEMORY.md-Chunks)",
        "payload_indexes": {
            "docid":         PayloadSchemaType.KEYWORD,
            "source":        PayloadSchemaType.KEYWORD,
            "dream_ts":      PayloadSchemaType.DATETIME,
            "session_count": PayloadSchemaType.INTEGER,
            "chunk_index":   PayloadSchemaType.INTEGER,
        },
    },
    "pkb_sessions": {
        "description": "Session-Transcripts (Gateway-Requests)",
        "payload_indexes": {
            "session_id":  PayloadSchemaType.KEYWORD,
            "user_id":     PayloadSchemaType.KEYWORD,
            "ts":          PayloadSchemaType.DATETIME,
            "channel":     PayloadSchemaType.KEYWORD,
            "summary":     PayloadSchemaType.TEXT,
            "chunk_index": PayloadSchemaType.INTEGER,
        },
    },
}


def setup_collections(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    logger.info("Vorhandene Collections: %s", existing)

    for name, cfg in COLLECTIONS.items():
        if name in existing:
            logger.info("Collection '%s' bereits vorhanden — übersprungen", name)
            continue

        logger.info("Erstelle Collection '%s' (%s)...", name, cfg["description"])
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
            hnsw_config=HnswConfigDiff(
                m=HNSW_M,
                ef_construct=HNSW_EF_CONSTRUCT,
                on_disk=False,
            ),
        )

        for field_name, schema_type in cfg["payload_indexes"].items():
            client.create_payload_index(
                collection_name=name,
                field_name=field_name,
                field_schema=schema_type,
            )
            logger.debug("  Index: %s (%s)", field_name, schema_type)

        logger.info("Collection '%s' erstellt mit %d Payload-Indizes",
                    name, len(cfg["payload_indexes"]))


def verify_collections(client: QdrantClient) -> bool:
    """Prüft ob alle Collections vorhanden und Dimension korrekt."""
    ok = True
    for name in COLLECTIONS:
        try:
            info = client.get_collection(name)
            dim = info.config.params.vectors.size
            if dim != EMBEDDING_DIM:
                logger.error("Collection '%s': Dimension %d != erwartet %d", name, dim, EMBEDDING_DIM)
                ok = False
            else:
                logger.info("Collection '%s': OK (dim=%d)", name, dim)
        except Exception as e:  # noqa: BLE001
            logger.error("Collection '%s': FEHLER — %s", name, e)
            ok = False
    return ok


if __name__ == "__main__":
    logger.info("Qdrant URL: %s", QDRANT_URL)
    logger.info("Embedding-Dim: %d", EMBEDDING_DIM)
    client = QdrantClient(url=QDRANT_URL, timeout=30)

    try:
        client.get_collections()  # Verbindungstest
    except Exception as e:
        logger.error("Qdrant nicht erreichbar: %s", e)
        sys.exit(1)

    setup_collections(client)

    if not verify_collections(client):
        logger.error("Verify fehlgeschlagen — Collections nicht korrekt angelegt")
        sys.exit(1)

    logger.info("Setup abgeschlossen. Alle %d Collections verifiziert.", len(COLLECTIONS))
    sys.exit(0)
