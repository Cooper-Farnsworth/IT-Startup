import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import User, Topic, Article, Notification
from app.neural_engine import neural_engine
from app.websocket_manager import ws_manager
import logging
import json

logger = logging.getLogger(__name__)

class RealtimeUpdater:
    """Real-time обновления статей и уведомлений"""
    
    def __init__(self, db_session_factory):
        self.db_factory = db_session_factory
        self.is_running = False
    
    async def check_new_articles(self):
        """Проверяет новые статьи и уведомляет пользователей"""
        while self.is_running:
            try:
                db = self.db_factory()
                
                # Получаем новые статьи
                fetcher = ArxivFetcher(db)
                new_papers = fetcher.fetch_new_papers(since_minutes=5)
                
                if new_papers:
                    logger.info(f"Processing {len(new_papers)} new papers")
                    
                    # Для каждой новой статьи определяем тему
                    for paper in new_papers:
                        # Определяем тему по категории
                        topic = self._determine_topic(paper['categories'], db)
                        if topic:
                            article = fetcher.save_article(paper, topic.id)
                            
                            if article:
                                # Генерируем эмбеддинг
                                combined_text = f"{article.title} [SEP] {article.abstract}"
                                embedding = neural_engine.get_embedding(combined_text)
                                article.combined_embedding = json.dumps(embedding.tolist())
                                db.commit()
                                
                                # Уведомляем заинтересованных пользователей
                                await self._notify_interested_users(article, db)
                
                db.close()
                
            except Exception as e:
                logger.error(f"Error checking new articles: {e}")
            
            # Ждем 30 секунд перед следующей проверкой
            await asyncio.sleep(30)
    
    def _determine_topic(self, categories: list, db: Session):
        """Определяет тему статьи по arXiv категории"""
        category_mapping = {
            'cs': 'Computer Science',
            'physics': 'Physics',
            'math': 'Mathematics',
            'q-bio': 'Biology',
            'eess': 'Engineering'
        }
        
        if categories:
            main_cat = categories[0].split('.')[0]
            topic_name = category_mapping.get(main_cat, 'General Science')
            return db.query(Topic).filter(Topic.name == topic_name).first()
        return None
    
    async def _notify_interested_users(self, article: Article, db: Session):
        """Уведомляет пользователей, которым может быть интересна статья"""
        # Получаем пользователей с этой темой
        users = db.query(User).filter(
            User.topics.any(id=article.topic_id)
        ).all()
        
        article_data = {
            'id': article.id,
            'title': article.title,
            'authors': article.authors,
            'abstract': article.abstract[:200],
            'url': article.url
        }
        
        for user in users:
            # Создаем уведомление в БД
            notification = Notification(
                user_id=user.id,
                title="Новая статья по вашей теме",
                message=f"Опубликована новая статья: {article.title[:100]}",
                article_id=article.id
            )
            db.add(notification)
            
            # Отправляем WebSocket уведомление
            await ws_manager.notify_new_article(user.id, article_data)
        
        db.commit()
        logger.info(f"Notified {len(users)} users about new article {article.id}")
    
    async def update_user_recommendations(self, user_id: int):
        """Обновляет рекомендации для пользователя в реальном времени"""
        db = self.db_factory()
        
        try:
            # Здесь можно пересчитать рекомендации для пользователя
            await ws_manager.notify_recommendations_updated(user_id)
            logger.info(f"Updated recommendations for user {user_id}")
        finally:
            db.close()
    
    async def start(self):
        """Запускает real-time обновления"""
        self.is_running = True
        logger.info("Realtime updater started")
        await self.check_new_articles()
    
    async def stop(self):
        """Останавливает обновления"""
        self.is_running = False
        logger.info("Realtime updater stopped")