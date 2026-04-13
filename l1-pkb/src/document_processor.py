"""RAG pipeline: document chunking, embedding, storage, retrieval, and generation."""

import hashlib
import logging
import uuid
from datetime import datetime, timezone

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from .config import config
from .embeddings import embed_batch, embed_text, get_embedding_dimension

logger = logging.getLogger(__name__)


def _get_qdrant() -> QdrantClient:
    return QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)


def _ensure_collection(client: QdrantClient) -> None:
    """Create the Qdrant collection if it doesn't exist."""
    collections = [c.name for c in client.get_collections().collections]
    if config.QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=get_embedding_dimension(),
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection: %s", config.QDRANT_COLLECTION)


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    chunk_words = config.CHUNK_SIZE
    overlap_words = config.CHUNK_OVERLAP

    for i in range(0, len(words), chunk_words - overlap_words):
        chunk = " ".join(words[i : i + chunk_words])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def ingest_document(
    content: str, metadata: dict | None = None
) -> dict:
    """Ingest a document: chunk, embed, store in Qdrant."""
    client = _get_qdrant()
    _ensure_collection(client)

    doc_id = str(uuid.uuid4())
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    meta = metadata or {}
    meta.update({
        "doc_id": doc_id,
        "content_hash": content_hash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })

    chunks = _chunk_text(content)
    if not chunks:
        return {"doc_id": doc_id, "chunks": 0, "status": "empty"}

    embeddings = embed_batch(chunks)

    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        points.append(
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    **meta,
                    "chunk_index": i,
                    "chunk_text": chunk,
                    "total_chunks": len(chunks),
                },
            )
        )

    client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)
    logger.info("Ingested document %s: %d chunks", doc_id, len(chunks))

    return {"doc_id": doc_id, "chunks": len(chunks), "status": "ingested"}


def query_documents(query: str, top_k: int | None = None) -> dict:
    """Query the PKB: embed query, retrieve context, generate response."""
    client = _get_qdrant()
    _ensure_collection(client)

    k = top_k or config.TOP_K
    query_embedding = embed_text(query)

    results = client.search(
        collection_name=config.QDRANT_COLLECTION,
        query_vector=query_embedding,
        limit=k,
    )

    if not results:
        return {
            "query": query,
            "answer": "No relevant documents found.",
            "sources": [],
        }

    context_chunks = []
    sources = []
    for result in results:
        chunk_text = result.payload.get("chunk_text", "")
        context_chunks.append(chunk_text)
        sources.append({
            "doc_id": result.payload.get("doc_id"),
            "title": result.payload.get("title", "Unknown"),
            "chunk_index": result.payload.get("chunk_index"),
            "score": result.score,
        })

    context = "\n\n---\n\n".join(context_chunks)
    answer = _generate_response(query, context)

    return {"query": query, "answer": answer, "sources": sources}


def _generate_response(query: str, context: str) -> str:
    """Generate a response using Ollama (local) with OpenRouter fallback."""
    prompt = (
        f"Based on the following context, answer the question.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )

    try:
        return _call_ollama(prompt)
    except Exception as e:
        logger.warning("Ollama failed: %s. Trying OpenRouter fallback.", e)

    if config.OPENROUTER_API_KEY:
        try:
            return _call_openrouter(prompt)
        except Exception as e:
            logger.error("OpenRouter fallback also failed: %s", e)

    return "Could not generate a response. Please check that Ollama is running."


def _call_ollama(prompt: str) -> str:
    """Call Ollama API for text generation."""
    url = f"http://{config.OLLAMA_HOST}:{config.OLLAMA_PORT}/api/generate"
    response = httpx.post(
        url,
        json={"model": config.OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["response"]


def _call_openrouter(prompt: str) -> str:
    """Call OpenRouter API as fallback."""
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.CLOUD_FALLBACK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def list_documents() -> list[dict]:
    """List all unique documents in the collection."""
    client = _get_qdrant()
    _ensure_collection(client)

    results = client.scroll(
        collection_name=config.QDRANT_COLLECTION,
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )

    seen = {}
    for point in results[0]:
        doc_id = point.payload.get("doc_id")
        if doc_id and doc_id not in seen:
            seen[doc_id] = {
                "doc_id": doc_id,
                "title": point.payload.get("title", "Unknown"),
                "source": point.payload.get("source", "Unknown"),
                "ingested_at": point.payload.get("ingested_at"),
                "total_chunks": point.payload.get("total_chunks", 0),
            }

    return list(seen.values())


def delete_document(doc_id: str) -> dict:
    """Delete all chunks belonging to a document."""
    client = _get_qdrant()
    _ensure_collection(client)

    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    client.delete(
        collection_name=config.QDRANT_COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        ),
    )
    logger.info("Deleted document: %s", doc_id)
    return {"doc_id": doc_id, "status": "deleted"}


def reassemble_document(doc_id: str) -> dict | None:
    """Reassemble all chunks of a document into full text, ordered by chunk_index."""
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    client = _get_qdrant()
    _ensure_collection(client)

    results = client.scroll(
        collection_name=config.QDRANT_COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        ),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    points = results[0]
    if not points:
        return None

    sorted_points = sorted(points, key=lambda p: p.payload.get("chunk_index", 0))
    chunks = [p.payload.get("chunk_text", "") for p in sorted_points]
    full_text = "\n\n".join(chunks)

    first = sorted_points[0].payload
    metadata = {
        "title": first.get("title", "Unknown"),
        "source": first.get("source", "Unknown"),
        "tags": first.get("tags", []),
        "ingested_at": first.get("ingested_at"),
        "content_hash": first.get("content_hash"),
    }

    return {
        "doc_id": doc_id,
        "content": full_text,
        "metadata": metadata,
        "chunks": len(sorted_points),
    }


def update_document(doc_id: str, content: str, metadata: dict | None = None) -> dict:
    """Update an existing document: delete old chunks, re-ingest new content."""
    client = _get_qdrant()
    _ensure_collection(client)

    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    client.delete(
        collection_name=config.QDRANT_COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        ),
    )

    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    meta = metadata or {}
    meta.update({
        "doc_id": doc_id,
        "content_hash": content_hash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })

    chunks = _chunk_text(content)
    if not chunks:
        return {"doc_id": doc_id, "chunks": 0, "status": "empty"}

    embeddings = embed_batch(chunks)

    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        points.append(
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    **meta,
                    "chunk_index": i,
                    "chunk_text": chunk,
                    "total_chunks": len(chunks),
                },
            )
        )

    client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)
    logger.info("Updated document %s: %d chunks", doc_id, len(chunks))

    return {"doc_id": doc_id, "chunks": len(chunks), "status": "updated"}


def export_all_documents() -> list[dict]:
    """Export all documents with full reassembled content."""
    docs = list_documents()
    exported = []
    for doc in docs:
        reassembled = reassemble_document(doc["doc_id"])
        if reassembled:
            exported.append(reassembled)
    return exported
