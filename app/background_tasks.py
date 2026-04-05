from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from app.database import SessionLocal, User, Article, UserVector
from app.neural_engine import neural_engine
import logging
import json
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def update_user_vectors():
    """Периодически обновляет векторы пользователей"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        updated = 0
        
        for user in users:
            if user.feedback_history:
                history = json.loads(user.feedback_history)
                liked_articles = [h for h in history if h.get('rating') == 'like']
                
                if liked_articles:
                    # Пересчитываем вектор
                    embeddings = []
                    for item in liked_articles[-50:]:  # Последние 50 лайков
                        if 'article_embedding' in item:
                            embeddings.append(np.array(item['article_embedding']))
                    
                    if embeddings:
                        new_vector = np.mean(embeddings, axis=0)
                        
                        if not user.vector:
                            user.vector = UserVector(user_id=user.id)
                        
                        user.vector.preference_vector = json.dumps(new_vector.tolist())
                        user.vector.last_updated = datetime.utcnow()
                        updated += 1
            
            if updated % 10 == 0:
                db.commit()
        
        db.commit()
        logger.info(f"Updated vectors for {updated} users")
        
    except Exception as e:
        logger.error(f"Error updating user vectors: {e}")
    finally:
        db.close()

def cleanup_old_notifications():
    """Удаляет старые уведомления"""
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        deleted = db.query(Notification).filter(
            Notification.created_at < cutoff_date,
            Notification.is_read == True
        ).delete()
        db.commit()
        logger.info(f"Deleted {deleted} old notifications")
    except Exception as e:
        logger.error(f"Error cleaning up notifications: {e}")
    finally:
        db.close()

def calculate_article_scores():
    """Пересчитывает релевантность статей"""
    db = SessionLocal()
    try:
        articles = db.query(Article).filter(
            Article.combined_embedding.isnot(None)
        ).limit(100).all()
        
        # Здесь можно пересчитать scores на основе popularity
        for article in articles:
            # Простая формула популярности
            likes_count = len([r for r in article.ratings if r.rating == 'like'])
            article.relevance_score = min(1.0, likes_count / 100)
        
        db.commit()
        logger.info(f"Updated scores for {len(articles)} articles")
        
    except Exception as e:
        logger.error(f"Error calculating scores: {e}")
    finally:
        db.close()

# Настройка периодических задач
scheduler.add_job(
    update_user_vectors,
    trigger=IntervalTrigger(hours=6),
    id='update_vectors',
    replace_existing=True
)

scheduler.add_job(
    cleanup_old_notifications,
    trigger=IntervalTrigger(days=1),
    id='cleanup_notifications',
    replace_existing=True
)

scheduler.add_job(
    calculate_article_scores,
    trigger=IntervalTrigger(hours=12),
    id='calculate_scores',
    replace_existing=True
)

def start_background_tasks():
    """Запускает фоновые задачи"""
    scheduler.start()
    logger.info("Background tasks started")

def stop_background_tasks():
    """Останавливает фоновые задачи"""
    scheduler.shutdown()
    logger.info("Background tasks stopped")