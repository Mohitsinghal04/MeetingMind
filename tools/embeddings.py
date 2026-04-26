"""
MeetingMind — Vertex AI Text Embeddings
Tries models in order of preference, falls back gracefully to None.
Semantic search still works via keyword fallback when embeddings unavailable.
"""

import logging
import os
from typing import Optional

_model = None
_model_name_used = None

# Try these models in order — first available wins
_CANDIDATE_MODELS = [
    "text-embedding-004",  # newest, 768-dim, widely available
    "text-embedding-005",  # if available
    "textembedding-gecko@003",  # older
    "textembedding-gecko@001",  # fallback
]


def _get_model():
    global _model, _model_name_used
    if _model is not None:
        return _model

    import vertexai
    from vertexai.language_models import TextEmbeddingModel

    project = os.getenv("PROJECT_ID")
    region = os.getenv("REGION", "us-central1")
    vertexai.init(project=project, location=region)

    for name in _CANDIDATE_MODELS:
        try:
            m = TextEmbeddingModel.from_pretrained(name)
            # Smoke-test with a tiny string
            m.get_embeddings(["test"])
            _model = m
            _model_name_used = name
            logging.info(f"Embedding model loaded: {name}")
            return _model
        except Exception as e:
            logging.warning(f"Embedding model {name} unavailable: {e}")

    logging.warning("No embedding model available — semantic search will use keyword fallback")
    return None


def get_embedding(text: str) -> Optional[list[float]]:
    """Return an embedding vector for text, or None on failure."""
    if not text or not text.strip():
        return None
    try:
        model = _get_model()
        if model is None:
            return None
        result = model.get_embeddings([text[:2048]])
        return result[0].values
    except Exception as e:
        logging.warning(f"Embedding failed (graceful degradation): {e}")
        return None


def get_embeddings_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Return embeddings for a batch of texts."""
    if not texts:
        return []
    try:
        model = _get_model()
        if model is None:
            return [None] * len(texts)
        results = model.get_embeddings([t[:2048] for t in texts])
        return [r.values for r in results]
    except Exception as e:
        logging.warning(f"Batch embedding failed, trying individually: {e}")
        return [get_embedding(t) for t in texts]
