"""
scheduler.py
------------
Runs the recommendation pipeline on a daily schedule.
Start with:  python scheduler.py
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from pipeline import run_pipeline
from app.logger import logger

scheduler = BlockingScheduler()
scheduler.add_job(run_pipeline, "interval", days=1, id="daily_pipeline")

logger.info("Scheduler started — pipeline runs every 24 hours.")

try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    logger.info("Scheduler stopped.")
