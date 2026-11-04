"""CPU semantic embeddings with no external inference API or credential."""
from functools import lru_cache
from pathlib import Path
from threading import Lock

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "embedding-models"
_lock = Lock()


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=MODEL_NAME, cache_dir=str(CACHE_DIR), threads=2)


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if any(not isinstance(text, str) for text in texts):
        raise ValueError("Embedding input must contain only strings.")
    with _lock:
        return [vector.tolist() for vector in _model().embed(texts, batch_size=16)]


def get_embedding(text: str) -> list[float]:
    return get_embeddings_batch([text])[0]
