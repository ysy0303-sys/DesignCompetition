from apscheduler.schedulers.background import BackgroundScheduler
from backed.database.session import SessionLocal
from backed.services.weekly_service import auto_generate_weekly

scheduler = BackgroundScheduler()

def job():
    db = SessionLocal()
    try:
        auto_generate_weekly(db)
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(job, "cron", hour=0, minute=0)
    scheduler.start()