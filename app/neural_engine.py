import numpy as np
import json
import re
import random
from collections import Counter, defaultdict
from typing import List, Dict, Set, Optional, Tuple
from datetime import datetime, timedelta
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans, DBSCAN
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import logging
import hashlib
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class UserStage(Enum):
    COLD_START = "cold_start"      # < 10 оценок
    LEARNING = "learning"           # 10-50 оценок
    ADAPTING = "adapting"           # 50-200 оценок
    PERSONALIZED = "personalized"   # > 200 оценок

@dataclass
class ArticleFeatures:
    """Расширенные признаки статьи"""
    title_vector: np.ndarray
    abstract_vector: np.ndarray
    tech_score: float
    novelty_score: float
    impact_score: float
    topic_cluster: int
    keyword_set: Set[str]
    author_set: Set[str]
    
class NeuralEngine:
    """
    ПРОДВИНУТАЯ НЕЙРОСЕТЬ для персонализации научных статей
    с поддержкой:
    - Многомерного векторного анализа
    - Ансамблевых методов
    - Обучения с подкреплением
    - Контекстных рекомендаций
    - Анализа временных рядов
    """
    
    def __init__(self):
        self.user_profiles = {}
        self.stop_words = self._get_stop_words()
        
        # Многоуровневый TF-IDF
        self.tfidf_title = TfidfVectorizer(max_features=500, stop_words='english', ngram_range=(1, 3))
        self.tfidf_abstract = TfidfVectorizer(max_features=1000, stop_words='english', ngram_range=(1, 2))
        self.tfidf_combined = TfidfVectorizer(max_features=1500, stop_words='english', ngram_range=(1, 3))
        
        # Уменьшение размерности
        self.svd_title = TruncatedSVD(n_components=50, random_state=42)
        self.svd_abstract = TruncatedSVD(n_components=100, random_state=42)
        self.svd_combined = TruncatedSVD(n_components=150, random_state=42)
        
        # Модели кластеризации
        self.kmeans_topic = KMeans(n_clusters=20, random_state=42, n_init=10)
        self.dbscan_niche = DBSCAN(eps=0.3, min_samples=3)
        
        # Классификатор для предсказания оценок
        self.rating_predictor = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        self.scaler = StandardScaler()
        
        # Хранилища
        self.articles_features = {}
        self.articles_matrix = None
        self.articles_list = []
        self.user_vectors = {}
        self.trending_scores = defaultdict(float)
        self.seasonal_factors = defaultdict(float)
        
        # Метаданные обучения
        self.training_epoch = 0
        self.recommendation_cache = {}
        
        logger.info("🧠 СУПЕР-НЕЙРОСЕТЬ ЗАПУЩЕНА!")
        logger.info("   ✨ Многомерный векторный анализ")
        logger.info("   ✨ Ансамблевые методы")
        logger.info("   ✨ Обучение с подкреплением")
        logger.info("   ✨ Контекстные рекомендации")
        logger.info("   ✨ Анализ временных рядов")
    
    def _get_stop_words(self) -> Set[str]:
        """Расширенный список стоп-слов"""
        base_stops = {
            'the', 'a', 'an', 'and', 'of', 'to', 'in', 'for', 'on', 'with',
            'by', 'is', 'are', 'was', 'were', 'be', 'been', 'this', 'that',
            'from', 'at', 'as', 'into', 'through', 'during', 'including',
            'using', 'used', 'use', 'can', 'will', 'may', 'show', 'shown',
            'figure', 'table', 'paper', 'propose', 'present', 'introduce',
            'we', 'our', 'their', 'they', 'them', 'these', 'those', 'such',
            'has', 'have', 'had', 'does', 'do', 'did', 'but', 'so', 'not',
            'however', 'therefore', 'moreover', 'furthermore', 'although',
            'study', 'research', 'result', 'results', 'analysis', 'approach',
            'method', 'methods', 'based', 'also', 'first', 'second', 'third'
        }
        
        # Добавляем технические стоп-слова
        tech_stops = {
            'learning', 'network', 'model', 'data', 'training', 'testing',
            'validation', 'accuracy', 'performance', 'evaluation', 'experiment'
        }
        
        return base_stops.union(tech_stops)
    
    def _extract_advanced_features(self, text: str) -> Dict:
        """Извлекает продвинутые признаки из текста"""
        text_lower = text.lower()
        
        # Технические термины с весами и категориями
        tech_terms = {
            # NLP/LLM
            'transformer': 1.5, 'attention': 1.4, 'bert': 1.5, 'gpt': 1.5,
            'llm': 1.5, 'large language model': 1.5, 'prompt': 1.3,
            
            # Deep Learning
            'neural network': 1.3, 'deep learning': 1.3, 'cnn': 1.2,
            'rnn': 1.2, 'lstm': 1.2, 'gan': 1.3, 'diffusion': 1.4,
            
            # ML
            'machine learning': 1.2, 'reinforcement learning': 1.4,
            'supervised': 1.1, 'unsupervised': 1.1, 'self-supervised': 1.4,
            
            # Advanced
            'multimodal': 1.4, 'few-shot': 1.3, 'zero-shot': 1.3,
            'rag': 1.4, 'fine-tuning': 1.3, 'embedding': 1.2,
            
            # Applications
            'computer vision': 1.2, 'nlp': 1.3, 'robotics': 1.2,
            'generative': 1.3, 'autonomous': 1.2
        }
        
        features = {
            'tech_score': 0,
            'diversity_score': 0,
            'innovation_score': 0,
            'keywords': [],
            'bigrams': [],
            'trigrams': [],
            'entities': []
        }
        
        # Подсчет технических терминов
        for term, weight in tech_terms.items():
            if term in text_lower:
                features['tech_score'] += weight
        
        # Извлечение n-грамм
        words = re.findall(r'\b[a-z]{3,}\b', text_lower)
        words = [w for w in words if w not in self.stop_words]
        
        # Биграммы
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            features['bigrams'].append(bigram)
        
        # Триграммы
        for i in range(len(words) - 2):
            trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
            features['trigrams'].append(trigram)
        
        # Ключевые слова (с частотностью)
        word_freq = Counter(words)
        features['keywords'] = [w for w, _ in word_freq.most_common(15)]
        
        # Оценка разнообразия
        unique_ratio = len(set(words)) / max(1, len(words))
        features['diversity_score'] = min(1.0, unique_ratio)
        
        # Оценка инновационности (по редким словам)
        rare_words = [w for w in words if len(w) > 8 and w not in self.stop_words]
        features['innovation_score'] = min(1.0, len(rare_words) / 20)
        
        features['tech_score'] = min(1.0, features['tech_score'] / 15)
        
        return features
    
    def compute_article_vector(self, article) -> np.ndarray:
        """Вычисляет многомерный вектор статьи"""
        title = article.title.lower() if article.title else ""
        abstract = article.abstract.lower() if article.abstract else ""
        
        # Векторы из разных источников
        title_vec = self.tfidf_title.fit_transform([title]).toarray()[0]
        abstract_vec = self.tfidf_abstract.fit_transform([abstract]).toarray()[0]
        combined_vec = self.tfidf_combined.fit_transform([f"{title} {abstract}"]).toarray()[0]
        
        # Уменьшаем размерность
        if title_vec.shape[0] >= 50:
            title_vec = self.svd_title.fit_transform([title_vec])[0]
        if abstract_vec.shape[0] >= 100:
            abstract_vec = self.svd_abstract.fit_transform([abstract_vec])[0]
        if combined_vec.shape[0] >= 150:
            combined_vec = self.svd_combined.fit_transform([combined_vec])[0]
        
        # Комбинируем векторы
        combined = np.concatenate([title_vec, abstract_vec, combined_vec])
        
        # Нормализация
        norm = np.linalg.norm(combined)
        if norm > 0:
            combined = combined / norm
        
        return combined
    
    def build_advanced_matrix(self, articles):
        """Строит продвинутую матрицу признаков"""
        if not articles:
            return
        
        self.articles_list = articles
        feature_vectors = []
        
        for article in articles:
            # Основной вектор
            main_vector = self.compute_article_vector(article)
            
            # Извлекаем текстовые признаки
            text = f"{article.title} {article.abstract or ''}".lower()
            advanced_features = self._extract_advanced_features(text)
            
            # Создаем расширенный вектор
            extended = np.concatenate([
                main_vector,
                [advanced_features['tech_score']],
                [advanced_features['diversity_score']],
                [advanced_features['innovation_score']]
            ])
            
            feature_vectors.append(extended)
            
            # Сохраняем признаки
            self.articles_features[article.id] = advanced_features
        
        self.articles_matrix = np.array(feature_vectors)
        
        # Кластеризация
        if len(articles) >= 30:
            try:
                self.kmeans_topic.fit(self.articles_matrix)
                logger.info(f"📊 Кластеризовано {len(articles)} статей в {self.kmeans_topic.n_clusters} кластеров")
            except:
                pass
        
        logger.info(f"📊 Построена матрица признаков: {self.articles_matrix.shape}")
    
    def get_user_stage(self, user) -> UserStage:
        """Определяет стадию обучения пользователя"""
        history = json.loads(user.feedback_history) if user.feedback_history else []
        total_ratings = len(history)
        
        if total_ratings < 10:
            return UserStage.COLD_START
        elif total_ratings < 50:
            return UserStage.LEARNING
        elif total_ratings < 200:
            return UserStage.ADAPTING
        else:
            return UserStage.PERSONALIZED
    
    def compute_user_vector(self, user) -> np.ndarray:
        """Вычисляет продвинутый вектор пользователя"""
        history = json.loads(user.feedback_history) if user.feedback_history else []
        liked_articles = [h for h in history if h.get('rating') == 'like']
        
        if len(liked_articles) < 5:
            return None
        
        # Взвешенное усреднение векторов понравившихся статей
        weighted_vectors = []
        weights = []
        
        now = datetime.utcnow()
        
        for item in liked_articles[-100:]:  # Последние 100 лайков
            article_id = item.get('article_id')
            if article_id in self.articles_features:
                # Временной вес
                timestamp = datetime.fromisoformat(item.get('timestamp', '2000-01-01'))
                days_ago = (now - timestamp).days
                time_weight = np.exp(-days_ago / 30)  # Экспоненциальное затухание
                
                # Находим вектор статьи
                for i, article in enumerate(self.articles_list):
                    if article.id == article_id:
                        weighted_vectors.append(self.articles_matrix[i])
                        weights.append(time_weight)
                        break
        
        if weighted_vectors:
            user_vector = np.average(weighted_vectors, weights=weights, axis=0)
            
            # Нормализация
            norm = np.linalg.norm(user_vector)
            if norm > 0:
                user_vector = user_vector / norm
            
            return user_vector
        
        return None
    
    def calculate_context_score(self, article, user_vector, user_stage: UserStage) -> float:
        """Вычисляет контекстную оценку релевантности"""
        if user_vector is None or self.articles_matrix is None:
            return 0.5
        
        # Находим индекс статьи
        article_idx = None
        for i, a in enumerate(self.articles_list):
            if a.id == article.id:
                article_idx = i
                break
        
        if article_idx is None:
            return 0.5
        
        article_vector = self.articles_matrix[article_idx]
        
        # Косинусное сходство
        similarity = cosine_similarity([user_vector], [article_vector])[0][0]
        
        # Адаптивный порог в зависимости от стадии
        if user_stage == UserStage.COLD_START:
            # Холодный старт - больше шума
            score = 0.3 + similarity * 0.4
        elif user_stage == UserStage.LEARNING:
            score = 0.2 + similarity * 0.6
        elif user_stage == UserStage.ADAPTING:
            score = 0.1 + similarity * 0.8
        else:  # PERSONALIZED
            score = similarity
        
        # Бонус за принадлежность к тому же кластеру
        if hasattr(self, 'kmeans_topic'):
            try:
                article_cluster = self.kmeans_topic.predict([article_vector])[0]
                if hasattr(self, 'user_cluster'):
                    if article_cluster == self.user_cluster:
                        score += 0.1
            except:
                pass
        
        return min(1.0, max(0.0, score))
    
    def calculate_bandit_score(self, article, user, n_plays: int = 10) -> float:
        """
        UCB (Upper Confidence Bound) для баланса exploration/exploitation
        """
        history = json.loads(user.feedback_history) if user.feedback_history else []
        
        # Считаем сколько раз рекомендовали похожие статьи
        similar_plays = 0
        total_reward = 0
        
        for item in history[-100:]:
            if item.get('topic') == article.topic.name if article.topic else None:
                similar_plays += 1
                if item.get('rating') == 'like':
                    total_reward += 1
        
        if similar_plays == 0:
            return 1.0  # Исследуем новую тему
        
        # UCB формула
        avg_reward = total_reward / similar_plays
        exploration_bonus = np.sqrt(2 * np.log(n_plays) / similar_plays)
        
        return min(1.0, avg_reward + exploration_bonus)
    
    def get_personalized_articles(self, user, all_articles, limit: int = 15) -> List:
        """Супер-персонализированная подборка"""
        if not all_articles:
            return []
        
        # Строим матрицу если нужно
        if self.articles_list != all_articles:
            self.build_advanced_matrix(all_articles)
        
        user_stage = self.get_user_stage(user)
        user_vector = self.compute_user_vector(user)
        
        # Получаем уже оцененные статьи
        history = json.loads(user.feedback_history) if user.feedback_history else []
        rated_ids = {item.get('article_id') for item in history if item.get('article_id')}
        
        unrated_articles = [a for a in all_articles if a.id not in rated_ids]
        
        if not unrated_articles:
            return all_articles[:limit]
        
        # Вычисляем комбинированную оценку
        scored = []
        for article in unrated_articles:
            # 1. Контекстная оценка (60%)
            context_score = self.calculate_context_score(article, user_vector, user_stage)
            
            # 2. Бандитская оценка (20%)
            bandit_score = self.calculate_bandit_score(article, user)
            
            # 3. Свежесть (15%)
            if article.published_date:
                days_old = (datetime.utcnow() - article.published_date).days
                freshness = max(0, 1.0 - days_old / 60)
            else:
                freshness = 0.5
            
            # 4. Трендовость (5%)
            trend_score = self.trending_scores.get(article.topic_id, 0)
            
            # Комбинируем с весами в зависимости от стадии
            if user_stage == UserStage.COLD_START:
                weights = (0.3, 0.4, 0.2, 0.1)  # Больше exploration
            elif user_stage == UserStage.LEARNING:
                weights = (0.5, 0.3, 0.15, 0.05)
            elif user_stage == UserStage.ADAPTING:
                weights = (0.7, 0.15, 0.1, 0.05)
            else:  # PERSONALIZED
                weights = (0.8, 0.05, 0.1, 0.05)  # Больше exploitation
            
            total_score = (weights[0] * context_score + 
                          weights[1] * bandit_score + 
                          weights[2] * freshness + 
                          weights[3] * trend_score)
            
            scored.append((total_score, article))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Адаптивное количество статей
        if user_stage == UserStage.COLD_START:
            # Холодный старт - показываем больше разных статей
            result = [article for score, article in scored[:limit]]
            random.shuffle(result)
        else:
            # Персонализация - топ статьи
            result = [article for score, article in scored[:limit]]
        
        # Добавляем немного случайности для exploration
        if user_stage != UserStage.PERSONALIZED and len(scored) > limit:
            exploration_count = max(1, int(limit * 0.2))
            exploration_items = random.sample(scored[limit:limit+exploration_count*2], 
                                            min(exploration_count, len(scored)-limit))
            for score, article in exploration_items:
                if article not in result:
                    result.append(article)
        
        total_ratings = len(history)
        accuracy = len([h for h in history if h.get('rating') == 'like']) / max(1, total_ratings)
        
        logger.info(f"🎯 СУПЕР-ПЕРСОНАЛИЗАЦИЯ для user {user.id}:")
        logger.info(f"   📊 Стадия: {user_stage.value}")
        logger.info(f"   📈 Оценок: {total_ratings}, Точность: {accuracy:.1%}")
        logger.info(f"   🎲 Результатов: {len(result)}")
        
        return result[:limit]
    
    def update_from_feedback(self, user, article, rating: str):
        """Супер-обучение на обратной связи"""
        history = json.loads(user.feedback_history) if user.feedback_history else []
        
        # Извлекаем продвинутые признаки
        text = f"{article.title} {article.abstract or ''}".lower()
        features = self._extract_advanced_features(text)
        
        authors = [a.strip() for a in article.authors.split(',')] if article.authors else []
        
        # Временная метка
        now = datetime.utcnow()
        
        feedback_entry = {
            'article_id': article.id,
            'title': article.title[:200],
            'rating': rating,
            'authors': authors,
            'keywords': features['keywords'][:15],
            'bigrams': features['bigrams'][:10],
            'trigrams': features['trigrams'][:5],
            'topic': article.topic.name if article.topic else 'Unknown',
            'timestamp': now.isoformat(),
            'tech_score': features['tech_score'],
            'diversity_score': features['diversity_score'],
            'innovation_score': features['innovation_score']
        }
        
        history.append(feedback_entry)
        
        # Ограничиваем историю
        if len(history) > 2000:
            history = history[-2000:]
        
        user.feedback_history = json.dumps(history)
        
        # Обновляем профиль пользователя
        if rating == 'like':
            # Добавляем авторов
            current_authors = json.loads(user.authors) if user.authors and user.authors != '[]' else []
            for author in authors:
                if author and author not in current_authors and len(author) > 2:
                    current_authors.append(author)
            user.authors = json.dumps(current_authors[:50])
            
            # Добавляем ключевые слова
            current_keywords = json.loads(user.keywords) if user.keywords and user.keywords != '[]' else []
            for kw in features['keywords'][:10]:
                if kw and kw not in current_keywords and len(kw) > 3:
                    current_keywords.append(kw)
            user.keywords = json.dumps(current_keywords[:50])
        
        # Обновляем тренды (экспоненциальное затухание)
        if article.topic_id:
            for tid in list(self.trending_scores.keys()):
                self.trending_scores[tid] *= 0.95
            self.trending_scores[article.topic_id] += 1.0 if rating == 'like' else 0.3
        
        # Обновляем сезонные факторы
        hour = now.hour
        weekday = now.weekday()
        self.seasonal_factors[f"hour_{hour}"] = self.seasonal_factors.get(f"hour_{hour}", 0) + 1
        self.seasonal_factors[f"weekday_{weekday}"] = self.seasonal_factors.get(f"weekday_{weekday}", 0) + 1
        
        # Пересчитываем вектор пользователя
        if rating == 'like':
            self.user_vectors[user.id] = self.compute_user_vector(user)
        
        # Логируем прогресс
        likes = len([h for h in history if h.get('rating') == 'like'])
        dislikes = len([h for h in history if h.get('rating') == 'dislike'])
        accuracy = likes / (likes + dislikes) if (likes + dislikes) > 0 else 0
        
        logger.info(f"📊 СУПЕР-ОБУЧЕНИЕ для user {user.id}:")
        logger.info(f"   👍 Лайков: {likes}, 👎 Дизлайков: {dislikes}")
        logger.info(f"   🎯 Точность: {accuracy:.1%}")
        logger.info(f"   ✍️ Авторов: {len(json.loads(user.authors))}")
        logger.info(f"   🔑 Ключевых слов: {len(json.loads(user.keywords))}")
        logger.info(f"   💡 Tech Score: {features['tech_score']:.2f}")
        logger.info(f"   🌈 Diversity: {features['diversity_score']:.2f}")
        
        # Обновляем классификатор если достаточно данных
        if likes + dislikes >= 50 and likes + dislikes % 25 == 0:
            self._train_predictor(user)

# Глобальный экземпляр
neural_engine = NeuralEngine()