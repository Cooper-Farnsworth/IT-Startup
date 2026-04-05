import numpy as np
import json
import re
import random
from collections import Counter
from typing import List, Dict, Set, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class NeuralEngine:
    """
    Нейросеть для персонализации научных статей
    """
    
    def __init__(self):
        self.user_profiles = {}
        self.stop_words = self._get_stop_words()
        logger.info("🧠 Нейросеть персонализации запущена")
    
    def _get_stop_words(self) -> Set[str]:
        """Стоп-слова для анализа"""
        return {
            'the', 'a', 'an', 'and', 'of', 'to', 'in', 'for', 'on', 'with',
            'by', 'is', 'are', 'was', 'were', 'be', 'been', 'this', 'that',
            'from', 'at', 'as', 'into', 'through', 'during', 'including',
            'using', 'used', 'use', 'can', 'will', 'may', 'show', 'shown',
            'figure', 'table', 'paper', 'propose', 'present', 'introduce',
            'we', 'our', 'their', 'they', 'them', 'these', 'those', 'such',
            'has', 'have', 'had', 'does', 'do', 'did', 'but', 'so', 'not'
        }
    
    def extract_author_preferences(self, history: List[Dict]) -> Dict[str, float]:
        """Анализирует предпочтения авторов"""
        author_scores = {}
        
        for item in history:
            if item.get('rating') == 'like':
                for author in item.get('authors', []):
                    author_scores[author] = author_scores.get(author, 0) + 1
            elif item.get('rating') == 'dislike':
                for author in item.get('authors', []):
                    author_scores[author] = author_scores.get(author, 0) - 0.5
        
        # Нормализуем
        if author_scores:
            max_score = max(author_scores.values())
            if max_score > 0:
                for author in author_scores:
                    author_scores[author] /= max_score
        
        return author_scores
    
    def extract_topic_preferences(self, user) -> Dict[str, float]:
        """Анализирует предпочтения по темам"""
        topic_scores = {}
        
        # Базовые темы пользователя
        for topic in user.topics:
            topic_scores[topic.name] = 1.0
        
        # Учитываем историю оценок
        if user.feedback_history:
            history = json.loads(user.feedback_history)
            for item in history:
                if 'topic' in item:
                    if item.get('rating') == 'like':
                        topic_scores[item['topic']] = topic_scores.get(item['topic'], 0) + 0.3
                    elif item.get('rating') == 'dislike':
                        topic_scores[item['topic']] = topic_scores.get(item['topic'], 0) - 0.3
        
        return topic_scores
    
    def extract_keyword_preferences(self, history: List[Dict]) -> Dict[str, float]:
        """Анализирует предпочтения по ключевым словам"""
        keyword_scores = {}
        
        for item in history:
            if item.get('rating') == 'like':
                for keyword in item.get('keywords', [])[:10]:
                    keyword_scores[keyword] = keyword_scores.get(keyword, 0) + 1
            elif item.get('rating') == 'dislike':
                for keyword in item.get('keywords', [])[:5]:
                    keyword_scores[keyword] = keyword_scores.get(keyword, 0) - 0.3
        
        # Нормализуем
        if keyword_scores:
            max_score = max(keyword_scores.values())
            if max_score > 0:
                for keyword in keyword_scores:
                    keyword_scores[keyword] /= max_score
        
        return keyword_scores
    
    def extract_frequent_words(self, text: str, top_k: int = 5) -> List[str]:
        """Извлекает топ-5 самых частотных слов из текста"""
        if not text:
            return []
        words = re.findall(r'\b[a-z]{4,}\b', text.lower())
        words = [w for w in words if w not in self.stop_words]
        word_freq = Counter(words)
        return [word for word, _ in word_freq.most_common(top_k)]
    
    def calculate_relevance_score(self, article, user_preferences: Dict) -> float:
        """
        Вычисляет релевантность статьи для пользователя
        """
        score = 0.0
        weights = {
            'topic': 0.35,      # Тематика
            'author': 0.30,     # Автор
            'keyword': 0.25,    # Ключевые слова
            'freshness': 0.10   # Свежесть
        }
        
        # 1. Тематика (35%)
        topic_score = user_preferences.get('topic_scores', {}).get(article.topic.name if article.topic else 'Unknown', 0)
        score += weights['topic'] * topic_score
        
        # 2. Авторы (30%)
        if article.authors:
            article_authors = [a.strip() for a in article.authors.split(',')]
            author_scores = user_preferences.get('author_scores', {})
            if author_scores:
                max_author_score = max(author_scores.values()) if author_scores else 1
                for author in article_authors:
                    score += weights['author'] * (author_scores.get(author, 0) / max_author_score)
        
        # 3. Ключевые слова (25%)
        article_text = (article.title + ' ' + (article.abstract or '')).lower()
        keyword_scores = user_preferences.get('keyword_scores', {})
        if keyword_scores:
            matched_keywords = 0
            for keyword, kw_score in keyword_scores.items():
                if keyword.lower() in article_text:
                    matched_keywords += kw_score
            keyword_match = min(1.0, matched_keywords / len(keyword_scores)) if keyword_scores else 0
            score += weights['keyword'] * keyword_match
        
        # 4. Свежесть (10%)
        if article.published_date:
            days_old = (datetime.utcnow() - article.published_date).days
            freshness = max(0, 1.0 - days_old / 365)
            score += weights['freshness'] * freshness
        
        return min(1.0, score)
    
    def get_user_preferences(self, user) -> Dict:
        """Получает полный профиль предпочтений пользователя"""
        history = json.loads(user.feedback_history) if user.feedback_history else []
        
        preferences = {
            'author_scores': self.extract_author_preferences(history),
            'topic_scores': self.extract_topic_preferences(user),
            'keyword_scores': self.extract_keyword_preferences(history),
            'total_likes': len([h for h in history if h.get('rating') == 'like']),
            'total_dislikes': len([h for h in history if h.get('rating') == 'dislike'])
        }
        
        return preferences
    
    def get_personalized_articles(self, user, all_articles, limit: int = 15) -> List:
        """
        Возвращает персонализированную подборку статей
        Использует нейросеть для ранжирования
        """
        if not all_articles:
            return []
        
        # Если статей меньше лимита, возвращаем все
        if len(all_articles) <= limit:
            return all_articles
        
        user_preferences = self.get_user_preferences(user)
        
        # Получаем уже оцененные статьи
        history = json.loads(user.feedback_history) if user.feedback_history else []
        rated_ids = {item['article_id'] for item in history}
        
        # Фильтруем неоценённые статьи
        unrated_articles = [a for a in all_articles if a.id not in rated_ids]
        
        # Если нет неоценённых, возвращаем любые статьи
        if not unrated_articles:
            return all_articles[:limit]
        
        # Вычисляем релевантность для каждой статьи
        scored = []
        for article in unrated_articles:
            relevance = self.calculate_relevance_score(article, user_preferences)
            scored.append((relevance, article))
        
        # Сортируем по релевантности
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Если у пользователя мало оценок (менее 10), показываем случайные статьи
        total_ratings = user_preferences['total_likes'] + user_preferences['total_dislikes']
        
        if total_ratings < 10:
            # Режим холодного старта - показываем случайные статьи
            import random
            result = random.sample(unrated_articles, min(limit, len(unrated_articles)))
            logger.info(f"Cold start mode: showing {len(result)} random articles")
            return result
        
        # Режим персонализации
        exploitation_count = max(3, int(limit * 0.7))  # Минимум 3 статьи для exploitation
        exploration_count = limit - exploitation_count
        
        result = []
        
        # Топ релевантные статьи (exploitation)
        for relevance, article in scored[:exploitation_count]:
            result.append(article)
        
        # Случайные статьи для exploration (если нужно)
        if exploration_count > 0:
            remaining = [a for a in unrated_articles if a not in result]
            if remaining:
                import random
                exploration_items = random.sample(remaining, min(exploration_count, len(remaining)))
                result.extend(exploration_items)
        
        # Если всё ещё меньше limit, добавляем из scored
        if len(result) < limit:
            remaining_scored = [a for relevance, a in scored if a not in result]
            if remaining_scored:
                result.extend(remaining_scored[:limit - len(result)])
        
        # Перемешиваем для разнообразия
        import random
        random.shuffle(result)
        
        logger.info(f"Personalized {len(result)} articles for user {user.id} "
                f"(total_ratings: {total_ratings}, limit: {limit})")
        
        return result[:limit]
    
    def update_from_feedback(self, user, article, rating: str):
        """Обновляет профиль пользователя на основе обратной связи"""
        history = json.loads(user.feedback_history) if user.feedback_history else []
        
        # Извлекаем ключевые слова из статьи
        article_text = (article.title + ' ' + (article.abstract or '')).lower()
        keywords = self.extract_frequent_words(article_text, 10)
        
        # Извлекаем авторов
        authors = [a.strip() for a in article.authors.split(',')] if article.authors else []
        
        # Вес оценки (лайк/дизлайк влияет сильнее, чем общая оценка подборки)
        weight = 1.0
        if rating == 'like':
            weight = 1.0
        elif rating == 'dislike':
            weight = -0.5
        
        history.append({
            'article_id': article.id,
            'title': article.title[:100],
            'rating': rating,
            'authors': authors,
            'keywords': keywords,
            'topic': article.topic.name if article.topic else 'Unknown',
            'timestamp': datetime.utcnow().isoformat(),
            'weight': weight
        })
        
        # Ограничиваем историю последними 500 событиями
        if len(history) > 500:
            history = history[-500:]
        
        user.feedback_history = json.dumps(history)
        
        # Обновляем вектор пользователя
        self._update_user_vector(user, authors, keywords, weight)
        
        # Логируем обновление профиля
        preferences = self.get_user_preferences(user)
        logger.info(f"📊 Профиль пользователя {user.id} обновлен: "
                f"лайков={preferences['total_likes']}, "
                f"дизлайков={preferences['total_dislikes']}, "
                f"авторов={len(preferences['author_scores'])}, "
                f"ключевых слов={len(preferences['keyword_scores'])}")

    def _update_user_vector(self, user, authors, keywords, weight):
        """Обновляет вектор предпочтений пользователя"""
        # Простая реализация - обновляем счётчики
        current_prefs = self.get_user_preferences(user)
        
        # Если есть вектор пользователя в БД, обновляем его
        if hasattr(user, 'vector') and user.vector:
            # Здесь можно обновлять embedding вектор
            pass

# Глобальный экземпляр
neural_engine = NeuralEngine()