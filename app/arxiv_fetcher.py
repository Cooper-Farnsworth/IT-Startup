import arxiv
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
import logging
import time

logger = logging.getLogger(__name__)

class ArxivFetcher:
    """Реальный сборщик статей с arXiv.org"""
    
    def __init__(self, db: Session):
        self.db = db
        self.client = arxiv.Client(
            page_size=100,
            delay_seconds=3,
            num_retries=3
        )
    
    def fetch_real_articles(self, category: str = "cs.AI", max_results: int = 100) -> List[Dict]:
        """
        Получает реальные статьи с arXiv
        
        Популярные категории:
        - cs.AI - Artificial Intelligence
        - cs.LG - Machine Learning  
        - cs.CL - Computation and Language (NLP)
        - cs.CV - Computer Vision
        - cs.IR - Information Retrieval
        - physics - Physics
        - math - Mathematics
        - q-bio - Quantitative Biology
        """
        logger.info(f"Fetching {max_results} real articles from arXiv category: {category}")
        
        try:
            search = arxiv.Search(
                query=f"cat:{category}",
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            articles = []
            for paper in self.client.results(search):
                article_data = {
                    'arxiv_id': paper.entry_id.split('/')[-1],
                    'title': paper.title.replace('\n', ' ').strip(),
                    'authors': ', '.join([a.name for a in paper.authors]),
                    'abstract': paper.summary.replace('\n', ' ').strip(),
                    'url': paper.entry_id,
                    'published_date': paper.published.replace(tzinfo=None) if paper.published else datetime.utcnow(),
                    'categories': paper.categories
                }
                articles.append(article_data)
                logger.debug(f"Fetched: {article_data['title'][:50]}...")
            
            logger.info(f"Successfully fetched {len(articles)} articles from arXiv")
            return articles
            
        except Exception as e:
            logger.error(f"Error fetching from arXiv: {e}")
            return []
    
    def fetch_by_keywords_real(self, keywords: List[str], max_results: int = 30) -> List[Dict]:
        """Ищет статьи по ключевым словам"""
        query = " AND ".join([f'all:"{kw}"' for kw in keywords[:3]])  # Ограничиваем 3 ключевыми словами
        
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
                sort_order=arxiv.SortOrder.Descending
            )
            
            articles = []
            for paper in self.client.results(search):
                article_data = {
                    'arxiv_id': paper.entry_id.split('/')[-1],
                    'title': paper.title.replace('\n', ' ').strip(),
                    'authors': ', '.join([a.name for a in paper.authors]),
                    'abstract': paper.summary.replace('\n', ' ').strip(),
                    'url': paper.entry_id,
                    'published_date': paper.published.replace(tzinfo=None) if paper.published else datetime.utcnow(),
                    'categories': paper.categories
                }
                articles.append(article_data)
            
            logger.info(f"Found {len(articles)} articles for keywords: {keywords}")
            return articles
            
        except Exception as e:
            logger.error(f"Error searching by keywords: {e}")
            return []
    
    def fetch_recent_papers(self, days_back: int = 7) -> List[Dict]:
        """Получает свежие статьи за последние N дней"""
        try:
            search = arxiv.Search(
                query="all:*",
                max_results=100,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            recent_articles = []
            
            for paper in self.client.results(search):
                if paper.published and paper.published.replace(tzinfo=None) >= cutoff_date:
                    article_data = {
                        'arxiv_id': paper.entry_id.split('/')[-1],
                        'title': paper.title.replace('\n', ' ').strip(),
                        'authors': ', '.join([a.name for a in paper.authors]),
                        'abstract': paper.summary.replace('\n', ' ').strip(),
                        'url': paper.entry_id,
                        'published_date': paper.published.replace(tzinfo=None),
                        'categories': paper.categories
                    }
                    recent_articles.append(article_data)
                
                if len(recent_articles) >= 50:
                    break
            
            logger.info(f"Found {len(recent_articles)} recent papers from last {days_back} days")
            return recent_articles
            
        except Exception as e:
            logger.error(f"Error fetching recent papers: {e}")
            return []
    
    def save_articles_to_db(self, articles_data: List[Dict], topic_id: int) -> int:
        """Сохраняет статьи в базу данных"""
        from app.database import Article
        
        saved_count = 0
        for article_data in articles_data:
            # Проверяем, есть ли уже такая статья
            existing = self.db.query(Article).filter(
                Article.arxiv_id == article_data['arxiv_id']
            ).first()
            
            if existing:
                continue
            
            # Создаем новую статью
            article = Article(
                arxiv_id=article_data['arxiv_id'],
                title=article_data['title'],
                authors=article_data['authors'],
                abstract=article_data['abstract'],
                url=article_data['url'],
                topic_id=topic_id,
                published_date=article_data['published_date'],
                is_new=True,
                discovered_at=datetime.utcnow()
            )
            
            self.db.add(article)
            saved_count += 1
        
        self.db.commit()
        logger.info(f"Saved {saved_count} new articles to database")
        return saved_count