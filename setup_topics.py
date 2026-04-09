#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Topic
from app.arxiv_direct import ArxivDirectParser
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_topics():
    """Инициализация тем для поиска"""
    db = SessionLocal()
    
    topics_data = [
        ("Artificial Intelligence", "cs.AI"),
        ("Machine Learning", "cs.LG"),
        ("Deep Learning", "cs.LG"),
        ("Computer Vision", "cs.CV"),
        ("Natural Language Processing", "cs.CL"),
        ("Robotics", "cs.RO"),
        ("Neural Networks", "cs.NE"),
        ("Computer Science", "cs"),
    ]
    
    for name, category in topics_data:
        existing = db.query(Topic).filter(Topic.name == name).first()
        if not existing:
            topic = Topic(name=name, arxiv_category=category, is_active=True)
            db.add(topic)
            logger.info(f"✅ Добавлена тема: {name}")
    
    db.commit()
    db.close()
    logger.info("🎉 Темы инициализированы!")

if __name__ == "__main__":
    setup_topics()