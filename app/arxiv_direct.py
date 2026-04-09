import arxiv
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import logging
import re
from sqlalchemy.orm import Session
from app.database import Article, Topic, ArticleRating

logger = logging.getLogger(__name__)

class ArxivDirectParser:
    """
    Прямой парсер arXiv с поддержкой:
    - Живого поиска по интересам пользователя
    - Динамического анализа релевантности
    - Персонализированной выдачи
    - Исключения уже показанных статей
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.client = arxiv.Client(
            delay_seconds=3,
            num_retries=3,
            page_size=100
        )
        # Хранилище показанных статей для каждого пользователя
        self.shown_articles_cache: Dict[int, Set[str]] = {}
    
    def get_shown_article_ids(self, user_id: int) -> Set[str]:
        """Получает ID уже показанных и оцененных статей пользователя"""
        if user_id in self.shown_articles_cache:
            return self.shown_articles_cache[user_id]
        
        # Получаем из БД все статьи, которые пользователь уже оценил
        rated_articles = self.db.query(ArticleRating).filter(
            ArticleRating.user_id == user_id
        ).all()
        
        shown_ids = set()
        for rating in rated_articles:
            if rating.article and rating.article.arxiv_id:
                shown_ids.add(rating.article.arxiv_id)
        
        # Также добавляем статьи из сессии (текущая подборка)
        from app.main import user_sessions
        session_key = f"user_{user_id}"
        if session_key in user_sessions:
            for article in user_sessions[session_key]:
                shown_ids.add(article['arxiv_id'])
        
        self.shown_articles_cache[user_id] = shown_ids
        return shown_ids
    
    def search_by_user_preferences(self, user, max_results: int = 100) -> List[Dict]:
        """
        Поиск статей по предпочтениям пользователя с исключением уже показанных
        """
        # Получаем уже показанные статьи
        shown_ids = self.get_shown_article_ids(user.id)
        logger.info(f"📊 Уже показано статей для user {user.id}: {len(shown_ids)}")
        
        # Строим поисковый запрос на основе интересов
        query_parts = []
        
        # 1. Темы пользователя
        user_topics = [t.name for t in user.topics]
        if user_topics:
            topic_keywords = self._topics_to_keywords(user_topics)
            query_parts.extend(topic_keywords)
        
        # 2. Ключевые слова пользователя
        import json
        keywords = json.loads(user.keywords) if user.keywords else []
        if keywords:
            query_parts.extend(keywords[:5])
        
        # 3. Авторы (если есть)
        authors = json.loads(user.authors) if user.authors else []
        if authors:
            author_queries = [f'au:"{author}"' for author in authors[:3]]
            query_parts.extend(author_queries)
        
        # Если нет предпочтений - берём популярные категории
        if not query_parts:
            query_parts = ['cat:cs.AI', 'cat:cs.LG', 'cat:cs.CL']
        
        search_query = ' OR '.join(query_parts[:10])
        logger.info(f"🔍 Поиск для user {user.id}: {search_query}")
        
        # Загружаем больше статей, чтобы учесть фильтрацию
        fetch_count = max_results + len(shown_ids) + 50
        articles = self._fetch_articles(search_query, fetch_count)
        
        # Фильтруем уже показанные статьи
        new_articles = [a for a in articles if a['arxiv_id'] not in shown_ids]
        
        logger.info(f"📊 После фильтрации: {len(new_articles)} новых статей из {len(articles)}")
        
        # Если новых статей мало, расширяем поиск
        if len(new_articles) < max_results:
            logger.info(f"⚠️ Мало новых статей ({len(new_articles)}), расширяем поиск...")
            # Добавляем общие категории
            expanded_query = f"({search_query}) OR cat:cs.AI OR cat:cs.LG OR cat:cs.CL"
            more_articles = self._fetch_articles(expanded_query, fetch_count * 2)
            for article in more_articles:
                if article['arxiv_id'] not in shown_ids and article not in new_articles:
                    new_articles.append(article)
        
        return new_articles[:max_results]
    
    def _topics_to_keywords(self, topics: List[str]) -> List[str]:
        """Преобразует темы в поисковые ключевые слова"""
        topic_map = {
            'Artificial Intelligence': 'cat:cs.AI',
            'Machine Learning': 'cat:cs.LG',
            'Deep Learning': 'deep learning OR neural network',
            'Computer Vision': 'cat:cs.CV',
            'Natural Language Processing': 'cat:cs.CL',
            'Robotics': 'cat:cs.RO',
            'Computer Science': 'cat:cs',
            'Physics': 'cat:physics',
            'Mathematics': 'cat:math'
        }
        
        keywords = []
        for topic in topics:
            if topic in topic_map:
                keywords.append(topic_map[topic])
            else:
                keywords.append(topic)
        return keywords
    
    def _fetch_articles(self, query: str, max_results: int) -> List[Dict]:
        """Загружает статьи из arXiv"""
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            articles = []
            for paper in self.client.results(search):
                articles.append({
                    'arxiv_id': paper.entry_id.split('/')[-1],
                    'title': paper.title.replace('\n', ' ').strip(),
                    'authors': ', '.join([a.name for a in paper.authors]),
                    'abstract': paper.summary.replace('\n', ' ').strip(),
                    'url': paper.entry_id,
                    'published_date': paper.published.replace(tzinfo=None) if paper.published else datetime.now(),
                    'categories': paper.categories,
                    'comment': paper.comment if hasattr(paper, 'comment') else ''
                })
            
            logger.info(f"✅ Загружено {len(articles)} статей по запросу")
            return articles
            
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке: {e}")
            return []
    
    def analyze_article_relevance(self, article: Dict, user, neural_engine) -> float:
        """
        Анализирует релевантность статьи для пользователя в реальном времени
        """
        score = 0.0
        total_weight = 0
        
        # 1. Тематическая релевантность (30%)
        user_topics = [t.name.lower() for t in user.topics]
        article_title = article['title'].lower()
        article_abstract = article['abstract'].lower()
        
        topic_score = 0
        for topic in user_topics:
            if topic in article_title or topic in article_abstract:
                topic_score += 0.3
        topic_score = min(0.3, topic_score)
        score += topic_score
        total_weight += 0.3
        
        # 2. Ключевые слова пользователя (25%)
        import json
        keywords = json.loads(user.keywords) if user.keywords else []
        if keywords:
            keyword_matches = sum(1 for kw in keywords if kw.lower() in article_title or kw.lower() in article_abstract)
            keyword_score = min(0.25, (keyword_matches / len(keywords)) * 0.25)
            score += keyword_score
        total_weight += 0.25
        
        # 3. Авторы (15%)
        authors = json.loads(user.authors) if user.authors else []
        if authors:
            article_authors_lower = article['authors'].lower()
            author_matches = sum(1 for author in authors if author.lower() in article_authors_lower)
            author_score = min(0.15, (author_matches / len(authors)) * 0.15)
            score += author_score
        total_weight += 0.15
        
        # 4. Свежесть статьи (15%)
        days_old = (datetime.now() - article['published_date']).days
        freshness = max(0, 0.15 * (1 - days_old / 90))
        score += freshness
        total_weight += 0.15
        
        # 5. Популярность (15%)
        popularity = 0
        if article.get('comment'):
            popularity += 0.07
        if len(article['abstract']) > 500:
            popularity += 0.04
        if len(article['authors'].split(',')) > 2:
            popularity += 0.04
        score += min(0.15, popularity)
        total_weight += 0.15
        
        return score / total_weight if total_weight > 0 else 0
    
    def save_article(self, article_data: Dict, topic_id: Optional[int] = None) -> Article:
        """Сохраняет статью в БД если её там нет"""
        
        existing = self.db.query(Article).filter(
            Article.arxiv_id == article_data['arxiv_id']
        ).first()
        
        if existing:
            return existing
        
        article = Article(
            arxiv_id=article_data['arxiv_id'],
            title=article_data['title'][:500],
            authors=article_data['authors'][:500],
            abstract=article_data['abstract'][:10000],
            url=article_data['url'],
            topic_id=topic_id,
            published_date=article_data['published_date'],
            discovered_at=datetime.utcnow(),
            is_new=True
        )
        
        self.db.add(article)
        self.db.commit()
        self.db.refresh(article)
        
        return article
    
    def clear_cache(self, user_id: int):
        """Очищает кэш показанных статей для пользователя"""
        if user_id in self.shown_articles_cache:
            del self.shown_articles_cache[user_id]