from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import SessionLocal, Topic
from app.arxiv_fetcher import ArxivFetcher
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def fetch_all_new_articles():
    db = SessionLocal()
    try:
        topics = db.query(Topic).filter(Topic.is_active == True).all()
        fetcher = ArxivFetcher(db)
        total_new = 0
        
        for topic in topics:
            if topic.arxiv_category:
                logger.info(f"Fetching articles for topic: {topic.name}")
                articles = fetcher.fetch_real_articles(category=topic.arxiv_category, max_results=500)
                saved = fetcher.save_articles_to_db(articles, topic.id)
                total_new += saved
                logger.info(f"Saved {saved} new articles for {topic.name}")
        
        logger.info(f"Total new articles fetched: {total_new}")
    except Exception as e:
        logger.error(f"Error fetching articles: {e}")
    finally:
        db.close()

scheduler.add_job(fetch_all_new_articles, trigger=IntervalTrigger(hours=6), id='fetch_all_articles', replace_existing=True)

def start_background_tasks():
    scheduler.start()
    logger.info("Background tasks started")

def stop_background_tasks():
    scheduler.shutdown()
    logger.info("Background tasks stopped")