"""
vector_store.py
---------------
FAISS-backed vector store.  The module exposes a single shared instance
(`_store`) that is lazily initialised on first access via `get_vector_store()`.
This avoids executing heavy work at import time.
"""

from __future__ import annotations

import numpy as np
import faiss

from app.config import EMBEDDING_DIM, FAISS_INDEX_FILE
from app.database import get_db
from app.embedder import from_blob
from app.logger import logger


class VectorStore:
    def __init__(self) -> None:
        self.index: faiss.Index = faiss.IndexFlatL2(EMBEDDING_DIM)
        self.event_ids: list[str] = []
        self._built: bool = False

    # ── Build ──────────────────────────────────────────────────────────────

    def build(self) -> int:
        """Load all embeddings from the DB and (re)build the FAISS index."""
        self.index = faiss.IndexFlatL2(EMBEDDING_DIM)
        self.event_ids = []

        with get_db() as (_, cursor):
            cursor.execute("SELECT event_id, embedding FROM events")
            rows = cursor.fetchall()

        embeddings: list[np.ndarray] = []
        for row in rows:
            if row["embedding"] is None:
                continue
            embeddings.append(from_blob(row["embedding"]))
            self.event_ids.append(row["event_id"])

        if embeddings:
            mat = np.array(embeddings, dtype="float32")
            self.index.add(mat)
            faiss.write_index(self.index, FAISS_INDEX_FILE)

        self._built = True
        logger.info("VectorStore built — %d events indexed.", len(self.event_ids))
        return len(self.event_ids)

    # ── Search ─────────────────────────────────────────────────────────────

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[tuple[str, float]]:
        """Return [(event_id, distance), ...] sorted by ascending distance."""
        if not self.event_ids:
            return []

        k = min(top_k, len(self.event_ids))
        query = np.array([query_embedding], dtype="float32")
        distances, indices = self.index.search(query, k)

        return [
            (self.event_ids[i], float(distances[0][pos]))
            for pos, i in enumerate(indices[0])
            if i < len(self.event_ids)
        ]

    @property
    def is_built(self) -> bool:
        return self._built and len(self.event_ids) > 0


# ── Module-level shared instance (lazy) ────────────────────────────────────

_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
