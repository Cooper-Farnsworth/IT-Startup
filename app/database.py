from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Table, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

# Ассоциативные таблицы
user_topics = Table('user_topics', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('topic_id', Integer, ForeignKey('topics.id'))
)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    # Настройки пользователя
    authors = Column(Text, default='[]')
    keywords = Column(Text, default='[]')
    
    # Для AI: история взаимодействий
    feedback_history = Column(Text, default='[]')
    
    # Real-time подписка
    ws_connected = Column(Boolean, default=False)
    last_notification = Column(DateTime)
    
    # Сохраняем ID показанных статей
    shown_articles = Column(Text, default='[]')  # JSON массив ID статей
    
    # Связи
    topics = relationship("Topic", secondary=user_topics, back_populates="user_list")
    ratings = relationship("ArticleRating", back_populates="user")
    vector = relationship("UserVector", back_populates="user", uselist=False)
    
class Topic(Base):
    __tablename__ = 'topics'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    arxiv_category = Column(String(100))
    is_active = Column(Boolean, default=True)
    
    # Связи - ИСПРАВЛЕНО: убрал back_populates="users" и заменил на другое имя
    user_list = relationship("User", secondary=user_topics, back_populates="topics")
    articles = relationship("Article", back_populates="topic")

class Article(Base):
    __tablename__ = 'articles'
    
    id = Column(Integer, primary_key=True)
    arxiv_id = Column(String(100), unique=True)
    title = Column(String(500))
    authors = Column(String(500))
    abstract = Column(Text)
    url = Column(String(500))
    topic_id = Column(Integer, ForeignKey('topics.id'))
    published_date = Column(DateTime)
    updated_date = Column(DateTime)
    
    # AI метаданные
    combined_embedding = Column(Text)
    citation_count = Column(Integer, default=0)
    relevance_score = Column(Float, default=0.0)
    
    # Real-time метаданные
    is_new = Column(Boolean, default=False)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    topic = relationship("Topic", back_populates="articles")
    ratings = relationship("ArticleRating", back_populates="article")

class ArticleRating(Base):
    __tablename__ = 'article_ratings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    article_id = Column(Integer, ForeignKey('articles.id'))
    rating = Column(String(10))  # 'like', 'dislike'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    user = relationship("User", back_populates="ratings")
    article = relationship("Article", back_populates="ratings")

class UserVector(Base):
    __tablename__ = 'user_vectors'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    preference_vector = Column(Text)
    last_updated = Column(DateTime, default=datetime.utcnow)
    total_feedbacks = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    dislikes_count = Column(Integer, default=0)
    
    # Связи
    user = relationship("User", back_populates="vector")

class BatchRating(Base):
    __tablename__ = 'batch_ratings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    rating = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = 'notifications'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    title = Column(String(200))
    message = Column(Text)
    article_id = Column(Integer, ForeignKey('articles.id'))
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    user = relationship("User")
    article = relationship("Article")

# Инициализация БД
engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///./data/science_distributor.db'), 
                       connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Инициализирует базу данных"""
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully")