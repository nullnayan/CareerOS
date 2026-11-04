"""
Vector Store Service — the bridge between CareerOS and Qdrant.

Responsibilities:
1. Initialize the Qdrant collection on first use (idempotent).
2. Chunk resume text into overlapping segments for semantic search.
3. Embed each chunk locally with BGE-small (no API key).
4. Upsert the resulting vectors into Qdrant with metadata payloads.
5. Query the store for the most relevant chunks given a question.

Why Qdrant + Postgres (not one or the other)?
- Postgres holds structured facts (skills, experience rows) — exact lookups.
- Qdrant holds semantic embeddings of free-text — fuzzy/meaning-based search.
- The RAG pipeline queries BOTH and merges results before prompting the LLM.
"""

import os
import uuid
import logging
from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from agents.llm_client import get_embedding, get_embeddings_batch

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "career_data_bge_small_v1"

# Keep legacy hosted vectors untouched; different models need separate collections.
EMBEDDING_DIM = 384

# Chunking config — 500 chars with 100 overlap is a good starting point
# for resume-length documents. Too small = fragments lose context,
# too large = embeddings become diluted.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100


def _get_client() -> QdrantClient:
    """Return a Qdrant client. Separated so we can mock it in tests."""
    return QdrantClient(url=QDRANT_URL)


def ensure_collection():
    """Create the collection if it doesn't already exist.
    Called at app startup and before first upsert — idempotent."""
    client = _get_client()
    collections = [c.name for c in client.get_collections().collections]

    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection '{COLLECTION_NAME}' ({EMBEDDING_DIM}d, cosine)")
    else:
        logger.info(f"Qdrant collection '{COLLECTION_NAME}' already exists — skipping creation")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping chunks.

    Why overlap? If a sentence like "Built a RAG pipeline using LangChain"
    falls right on a chunk boundary, the overlap ensures it appears fully
    in at least one chunk — so the embedding captures the full meaning.
    """
    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def embed_and_upsert_resume(
    user_id: str,
    resume_version_id: str,
    raw_text: str,
    source_filename: Optional[str] = None,
):
    """
    The main pipeline: chunk → embed → upsert into Qdrant.

    Each point's payload stores enough metadata to trace back to the
    exact resume version and user, which the RAG chat will use to
    cite its sources ("this answer came from resume version X").
    """
    ensure_collection()
    client = _get_client()

    chunks = chunk_text(raw_text)
    if not chunks:
        logger.warning(f"No chunks generated for resume {resume_version_id} — skipping embedding")
        return 0

    try:
        embeddings = get_embeddings_batch(chunks)
    except Exception as e:
        logger.error(f"Failed to batch embed chunks of resume {resume_version_id}: {e}")
        return 0

    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        if embedding is None:
            continue
        point = PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{COLLECTION_NAME}:{user_id}:{resume_version_id}:{i}")),
            vector=embedding,
            payload={
                "user_id": user_id,
                "resume_version_id": resume_version_id,
                "chunk_index": i,
                "chunk_text": chunk,
                "source_filename": source_filename,
                "source_type": "resume",
            },
        )
        points.append(point)

    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(
            f"Upserted {len(points)} chunks for resume {resume_version_id} "
            f"(user {user_id}) into Qdrant"
        )

    return len(points)


def search_similar(
    user_id: str,
    query_text: str,
    top_k: int = 5,
) -> List[dict]:
    """
    Search Qdrant for the most relevant chunks belonging to a specific user.

    Returns a list of dicts with chunk_text, score, and metadata —
    ready to be injected into the RAG prompt as context.
    """
    ensure_collection()
    client = _get_client()

    query_embedding = get_embedding(query_text)

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id),
                )
            ]
        ),
        limit=top_k,
    )

    return [
        {
            "chunk_text": hit.payload.get("chunk_text", ""),
            "score": hit.score,
            "resume_version_id": hit.payload.get("resume_version_id"),
            "source_filename": hit.payload.get("source_filename"),
            "chunk_index": hit.payload.get("chunk_index"),
        }
        for hit in results
    ]


def delete_resume_vectors(user_id: str, resume_version_id: str):
    """Remove all vectors for a specific resume version.
    Called when a user deletes a resume, so stale embeddings don't
    pollute search results."""
    client = _get_client()

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="resume_version_id", match=MatchValue(value=resume_version_id)),
            ]
        ),
    )
    logger.info(f"Deleted vectors for resume {resume_version_id} (user {user_id})")
