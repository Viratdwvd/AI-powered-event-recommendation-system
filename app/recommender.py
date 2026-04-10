"""
recommender.py
--------------
Core recommendation logic.

Bug fixed: the original code called `get_feedback_weight()` inside a loop,
opening a new DB connection per candidate event — O(N) round-trips.
This version fetches all relevant feedback rows in a single batched query.
"""

from __future__ import annotations

from app.embedder import generate_embedding
from app.vector_store import get_vector_store
from app.config import TOP_K
from app.database import get_db


def _get_feedback_weights(user_email: str, event_ids: list[str]) -> dict[str, float]:
    """
    Return {event_id: weight} for all given event_ids in one DB round-trip.
    Weight = avg_rating * 0.1  (so a 5-star review adds +0.5 to the score).
    """
    if not event_ids:
        return {}

    placeholders = ",".join("?" * len(event_ids))
    with get_db() as (_, cursor):
        cursor.execute(
            f"""
            SELECT event_id, AVG(rating) AS avg_rating
            FROM feedback
            WHERE user_email = ? AND event_id IN ({placeholders})
            GROUP BY event_id
            """,
            [user_email, *event_ids],
        )
        return {
            row["event_id"]: (row["avg_rating"] or 0.0) * 0.1
            for row in cursor.fetchall()
        }


def recommend_for_user(email: str, interests: str, top_k: int = TOP_K) -> list[str]:
    """
    Return a list of up to `top_k` event_ids ranked by relevance to the
    user's interests, boosted by their historical feedback.
    """
    store = get_vector_store()
    if not store.is_built:
        return []

    query_embedding = generate_embedding(interests.lower().strip())
    candidates = store.search(query_embedding, top_k=top_k * 4)  # over-fetch for re-ranking

    candidate_ids = [eid for eid, _ in candidates]
    feedback_weights = _get_feedback_weights(email, candidate_ids)

    scored = []
    for event_id, distance in candidates:
        similarity = 1.0 / (1.0 + distance)
        boost = feedback_weights.get(event_id, 0.0)
        scored.append((event_id, 0.85 * similarity + boost))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [eid for eid, _ in scored[:top_k]]
