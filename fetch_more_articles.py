#!/usr/bin/env python
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Topic, Article
from app.arxiv_fetcher import ArxivFetcher
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_more_articles():
    """Загружает больше реальных статей с arXiv"""
    db = SessionLocal()
    
    try:
        # Проверяем текущее количество статей
        current_count = db.query(Article).count()
        logger.info(f"Current articles in DB: {current_count}")
        
        # Создаем fetcher
        fetcher = ArxivFetcher(db)
        
        # Категории для загрузки с реальными названиями
        categories = {
            "cs.AI": "Artificial Intelligence",
            "cs.LG": "Machine Learning", 
            "cs.CL": "Natural Language Processing",
            "cs.CV": "Computer Vision",
            "cs.IR": "Information Retrieval",
            "cs.RO": "Robotics",
            "cs.CR": "Cryptography",
            "cs.DB": "Databases",
            "cs.GT": "Game Theory",
            "cs.NE": "Neural Networks"
        }
        
        total_new = 0
        
        for arxiv_cat, topic_name in categories.items():
            # Находим тему или создаем
            topic = db.query(Topic).filter(Topic.name == topic_name).first()
            if not topic:
                topic = Topic(name=topic_name, arxiv_category=arxiv_cat)
                db.add(topic)
                db.commit()
                db.refresh(topic)
                logger.info(f"Created new topic: {topic_name}")
            
            logger.info(f"\n📚 Fetching articles for {topic_name} (cat: {arxiv_cat})...")
            
            # Загружаем статьи
            articles = fetcher.fetch_real_articles(category=arxiv_cat, max_results=30)
            
            if articles:
                saved = fetcher.save_articles_to_db(articles, topic.id)
                total_new += saved
                logger.info(f"✅ Saved {saved} new articles for {topic_name}")
            else:
                logger.warning(f"⚠️ No articles fetched for {topic_name}")
        
        # Финальная статистика
        final_count = db.query(Article).count()
        logger.info(f"\n{'='*50}")
        logger.info(f"✅ Fetch complete!")
        logger.info(f"📊 Articles before: {current_count}")
        logger.info(f"📊 Articles added: {total_new}")
        logger.info(f"📊 Articles now: {final_count}")
        logger.info(f"{'='*50}")
        
        # Показываем несколько примеров
        sample_articles = db.query(Article).limit(5).all()
        logger.info("\n📄 Sample articles in database:")
        for i, article in enumerate(sample_articles, 1):
            logger.info(f"  {i}. {article.title[:80]}...")
            logger.info(f"     Authors: {article.authors[:60]}...")
            logger.info(f"     URL: {article.url}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    fetch_more_articles()