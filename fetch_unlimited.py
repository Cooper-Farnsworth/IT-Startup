#!/usr/bin/env python
"""
Безлимитная загрузка статей с arXiv - БЕЗ ПАРАМЕТРА START
Запуск: python fetch_unlimited.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Topic, Article
import arxiv
from datetime import datetime, timedelta
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Категории для загрузки
CATEGORIES = {
    "cs.AI": "Artificial Intelligence",
    "cs.LG": "Machine Learning",
    "cs.CL": "Natural Language Processing",
    "cs.CV": "Computer Vision",
    "cs.NE": "Neural Networks",
}

def fetch_by_date_range():
    """
    Загружает статьи по датам - самый надежный способ
    """
    db = SessionLocal()
    client = arxiv.Client(delay_seconds=5, num_retries=3)
    
    for arxiv_cat, topic_name in CATEGORIES.items():
        logger.info(f"\n{'='*50}")
        logger.info(f"📚 Загрузка: {topic_name} ({arxiv_cat})")
        logger.info(f"{'='*50}")
        
        # Получаем или создаем тему
        topic = db.query(Topic).filter(Topic.arxiv_category == arxiv_cat).first()
        if not topic:
            topic = Topic(name=topic_name, arxiv_category=arxiv_cat, is_active=True)
            db.add(topic)
            db.commit()
            db.refresh(topic)
        
        # Загружаем статьи по месяцам (последние 24 месяца)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)  # 2 года назад
        
        current_start = start_date
        total_saved = 0
        month_count = 0
        
        while current_start < end_date and month_count < 24:
            current_end = current_start + timedelta(days=30)
            if current_end > end_date:
                current_end = end_date
            
            date_query = f"submittedDate:[{current_start.strftime('%Y%m%d')} TO {current_end.strftime('%Y%m%d')}]"
            query = f"cat:{arxiv_cat} AND {date_query}"
            
            logger.info(f"   📅 Период: {current_start.date()} - {current_end.date()}")
            
            try:
                search = arxiv.Search(
                    query=query,
                    max_results=2000,
                    sort_by=arxiv.SortCriterion.SubmittedDate,
                    sort_order=arxiv.SortOrder.Descending
                )
                
                saved_in_period = 0
                for paper in client.results(search):
                    # Проверяем, есть ли уже в БД
                    existing = db.query(Article).filter(Article.arxiv_id == paper.entry_id.split('/')[-1]).first()
                    if existing:
                        continue
                    
                    article = Article(
                        arxiv_id=paper.entry_id.split('/')[-1],
                        title=paper.title.replace('\n', ' ').strip()[:500],
                        authors=', '.join([a.name for a in paper.authors])[:500],
                        abstract=paper.summary.replace('\n', ' ').strip()[:10000],
                        url=paper.entry_id,
                        topic_id=topic.id,
                        published_date=paper.published.replace(tzinfo=None) if paper.published else datetime.now(),
                        is_new=True,
                        discovered_at=datetime.now()
                    )
                    db.add(article)
                    saved_in_period += 1
                    
                    if saved_in_period % 50 == 0:
                        db.commit()
                        logger.info(f"      Сохранено {saved_in_period} статей...")
                
                if saved_in_period > 0:
                    db.commit()
                    total_saved += saved_in_period
                    logger.info(f"      ✅ Добавлено {saved_in_period} статей за период")
                else:
                    logger.info(f"      ℹ️ Новых статей нет")
                
            except Exception as e:
                logger.error(f"      ❌ Ошибка: {e}")
            
            current_start = current_end
            month_count += 1
            time.sleep(5)  # Пауза между периодами
        
        logger.info(f"📊 Итого для {topic_name}: +{total_saved} статей")
        time.sleep(10)  # Пауза между категориями
    
    db.close()
    logger.info("\n🎉 ЗАГРУЗКА ЗАВЕРШЕНА!")

def fetch_simple():
    """
    Простая загрузка - максимум 2000 статей на категорию
    """
    db = SessionLocal()
    client = arxiv.Client(delay_seconds=3, num_retries=3)
    
    for arxiv_cat, topic_name in CATEGORIES.items():
        logger.info(f"\n📚 Загрузка: {topic_name} ({arxiv_cat})")
        
        topic = db.query(Topic).filter(Topic.arxiv_category == arxiv_cat).first()
        if not topic:
            topic = Topic(name=topic_name, arxiv_category=arxiv_cat, is_active=True)
            db.add(topic)
            db.commit()
            db.refresh(topic)
        
        try:
            search = arxiv.Search(
                query=f"cat:{arxiv_cat}",
                max_results=2000,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            saved = 0
            for paper in client.results(search):
                existing = db.query(Article).filter(Article.arxiv_id == paper.entry_id.split('/')[-1]).first()
                if existing:
                    continue
                
                article = Article(
                    arxiv_id=paper.entry_id.split('/')[-1],
                    title=paper.title[:500],
                    authors=', '.join([a.name for a in paper.authors])[:500],
                    abstract=paper.summary[:10000],
                    url=paper.entry_id,
                    topic_id=topic.id,
                    published_date=paper.published.replace(tzinfo=None) if paper.published else datetime.now(),
                    discovered_at=datetime.now()
                )
                db.add(article)
                saved += 1
                
                if saved % 100 == 0:
                    db.commit()
                    logger.info(f"   Сохранено {saved} статей...")
            
            db.commit()
            logger.info(f"✅ Для {topic_name} добавлено {saved} статей")
            
        except Exception as e:
            logger.error(f"Ошибка для {arxiv_cat}: {e}")
        
        time.sleep(5)
    
    db.close()

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║              FETCHER - БЕЗ ОШИБКИ START                         ║
    ║                                                                  ║
    ║   Выберите режим:                                               ║
    ║   1. Простая загрузка (до 2000 статей на тему)                  ║
    ║   2. Загрузка по датам (больше статей, но дольше)               ║
    ║                                                                  ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    
    choice = input("Ваш выбор (1/2): ")
    
    if choice == '1':
        fetch_simple()
    elif choice == '2':
        fetch_by_date_range()
    else:
        print("Выход...")