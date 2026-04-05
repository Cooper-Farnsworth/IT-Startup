#!/usr/bin/env python
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Article
from datetime import datetime, timedelta

db = SessionLocal()

# Смотрим, когда были добавлены последние статьи
latest_article = db.query(Article).order_by(Article.discovered_at.desc()).first()

if latest_article:
    print(f"📊 Последняя добавленная статья:")
    print(f"   Название: {latest_article.title[:80]}...")
    print(f"   Добавлена: {latest_article.discovered_at}")
    print(f"   { (datetime.utcnow() - latest_article.discovered_at).seconds // 60 } минут назад")
else:
    print("❌ Статей нет в базе")

# Считаем статьи по дням
today = datetime.utcnow().date()
week_ago = today - timedelta(days=7)

new_today = db.query(Article).filter(Article.discovered_at >= today).count()
new_week = db.query(Article).filter(Article.discovered_at >= week_ago).count()

print(f"\n📈 Статистика обновлений:")
print(f"   Добавлено сегодня: {new_today}")
print(f"   Добавлено за неделю: {new_week}")
print(f"   Всего статей: {db.query(Article).count()}")

db.close()