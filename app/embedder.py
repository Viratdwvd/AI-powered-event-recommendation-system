"""
embedder.py
-----------
Wraps SentenceTransformer with lazy loading so the ~90 MB model is only
downloaded/loaded when the first embedding is actually requested — not at
import time.  This keeps cold-start times fast for the Streamlit UI.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer
from app.config import EMBEDDING_MODEL

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def generate_embedding(text: str) -> np.ndarray:
    return _get_model().encode(text)


def to_blob(embedding: np.ndarray) -> bytes:
    return embedding.astype("float32").tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="float32")
