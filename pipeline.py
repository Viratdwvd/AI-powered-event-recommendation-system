"""
pipeline.py  —  headless runner.  Run with: python pipeline.py
Uses the live EventHub scraper as data source.
"""
from app.database      import create_tables
from app.scraper        import scrape_eventhub
from app.event_storage  import save_events, save_scrape_meta
from app.vector_store   import get_vector_store
from app.recommender    import recommend_for_user
from app.email_service  import send_email
from app.user_service   import get_all_users
from app.logger         import logger


def run_pipeline() -> None:
    logger.info("Pipeline starting…")
    create_tables()

    result = scrape_eventhub()
    save_scrape_meta(result.status, len(result.events), result.message)

    if result.status != "ok" or not result.events:
        logger.error("Scrape failed (%s): %s", result.status, result.message)
        return

    n = save_events(result.events)
    logger.info("%d events saved.", n)

    count = get_vector_store().build()
    logger.info("%d events indexed.", count)

    for email, interests in get_all_users():
        recs = recommend_for_user(email, interests)
        if recs:
            ok = send_email(email, recs)
            logger.info("Email %s → %s", "sent" if ok else "FAILED", email)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    run_pipeline()
