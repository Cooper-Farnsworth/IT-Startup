from fastapi import FastAPI, Request, Form, HTTPException, Depends, Cookie, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import Optional, List, Dict
import json
from datetime import datetime
import logging
import os
import random
import asyncio
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.database import (
    SessionLocal, User, Topic, Article, ArticleRating, 
    BatchRating, Notification, init_db
)
from app.neural_engine import neural_engine
from app.websocket_manager import ws_manager
from app.arxiv_direct import ArxivDirectParser

app = FastAPI(title="Science Distributor - Real Articles from arXiv")
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"))
templates = Jinja2Templates(directory="app/templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Хранилище активных сессий пользователей (текущие статьи)
user_sessions = {}
# Хранилище последнего запроса для каждого пользователя
user_last_query = {}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
async def startup_event():
    init_db()
    logger.info("✅ Система запущена")

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await ws_manager.connect(user_id, websocket)
    try:
        await websocket.send_json({'type': 'connected', 'message': 'Connected'})
        while True:
            data = await websocket.receive_text()
            if data == 'ping':
                await websocket.send_text('pong')
            elif data == 'refresh':
                await ws_manager.send_personal_message(user_id, {'type': 'refresh_needed', 'message': 'Refresh your recommendations'})
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id)

# ============ АВТОРИЗАЦИЯ ============

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered"})
    hashed_password = pwd_context.hash(password)
    user = User(email=email, password_hash=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    response = RedirectResponse(url="/settings", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id))
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id))
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("user_id")
    return response

# ============ DASHBOARD ============

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not user_id:
        return RedirectResponse(url="/login")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login")
    
    user_topics = [t for t in user.topics] if user.topics else []
    
    if not user_topics:
        return templates.TemplateResponse("dashboard.html", {
            "request": request, "user": user, "articles": [], "user_ratings": {},
            "ws_url": f"ws://localhost:8000/ws/{user.id}",
            "no_articles_message": "Пожалуйста, выберите темы в настройках", 
            "total_rated": 0,
            "live_mode": True
        })
    
    session_key = f"user_{user.id}"
    
    # Получаем оценки пользователя
    user_ratings_dict = {}
    ratings = db.query(ArticleRating).join(Article).filter(ArticleRating.user_id == user.id).all()
    for rating in ratings:
        if rating.article and rating.article.arxiv_id:
            user_ratings_dict[rating.article.arxiv_id] = rating.rating
    
    # ПРОВЕРЯЕМ: есть ли уже сохраненные статьи в сессии
    if session_key in user_sessions and user_sessions[session_key]:
        articles_data = user_sessions[session_key]
        logger.info(f"📚 Используем сохраненную сессию для user {user.id}: {len(articles_data)} статей")
    else:
        # Если сессии нет - ЗАГРУЖАЕМ статьи ПЕРВЫЙ РАЗ
        logger.info(f"🆕 Первая загрузка статей для user {user.id}")
        articles_data = await get_fresh_recommendations(user, db, limit=15)
        user_sessions[session_key] = articles_data
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "articles": articles_data,
        "user_ratings": user_ratings_dict, "ws_url": f"ws://localhost:8000/ws/{user.id}",
        "live_mode": True, "total_rated": len([r for r in ratings if r.rating in ['like', 'dislike']])
    })

async def get_fresh_recommendations(user, db: Session, limit: int = 15) -> List[Dict]:
    """Получает свежие рекомендации на основе текущих предпочтений"""
    
    arxiv_parser = ArxivDirectParser(db)
    
    # Получаем персонализированные статьи напрямую из arXiv
    fresh_articles = neural_engine.get_personalized_recommendations_direct(
        user, arxiv_parser, limit=limit
    )
    
    # Сохраняем статьи в БД и формируем ответ
    articles_data = []
    for article_data in fresh_articles:
        # Определяем тему
        topic_id = None
        if article_data.get('categories'):
            main_cat = article_data['categories'][0].split('.')[0] if article_data['categories'] else None
            topic = db.query(Topic).filter(Topic.arxiv_category.like(f'{main_cat}%')).first()
            if topic:
                topic_id = topic.id
        
        # Сохраняем в БД
        saved_article = arxiv_parser.save_article(article_data, topic_id)
        
        articles_data.append({
            'arxiv_id': saved_article.arxiv_id,
            'title': saved_article.title,
            'authors': saved_article.authors,
            'abstract': saved_article.abstract if saved_article.abstract else '',
            'url': saved_article.url,
            'topic_id': saved_article.topic_id,
            'topic_name': saved_article.topic.name if saved_article.topic else 'Science'
        })
    
    return articles_data

# ============ PROFILE ============

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """Страница профиля пользователя"""
    if not user_id:
        return RedirectResponse(url="/login")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

# ============ SETTINGS ============

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not user_id:
        return RedirectResponse(url="/login")
    user = db.query(User).filter(User.id == int(user_id)).first()
    topics = db.query(Topic).all()
    user_topics = [t.id for t in user.topics] if user.topics else []
    user_authors = ", ".join(json.loads(user.authors)) if user.authors and user.authors != '[]' else ""
    user_keywords = ", ".join(json.loads(user.keywords)) if user.keywords and user.keywords != '[]' else ""
    return templates.TemplateResponse("settings.html", {"request": request, "user": user,
        "topics": topics, "user_topics": user_topics, "user_authors": user_authors, "user_keywords": user_keywords})

@app.post("/settings")
async def save_settings(request: Request, topics: List[int] = Form([]), authors: str = Form(""),
                        keywords: str = Form(""), confirm_reset: Optional[str] = Form(None),
                        user_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not user_id:
        return RedirectResponse(url="/login")
    user = db.query(User).filter(User.id == int(user_id)).first()
    
    old_topics = set([t.id for t in user.topics])
    new_topics = set(topics)
    if old_topics != new_topics and not confirm_reset:
        return JSONResponse({"warning": "Смена темы приведёт к сбросу данных обучения", "needs_confirmation": True})
    
    user.topics = []
    for topic_id in topics:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if topic:
            user.topics.append(topic)
    
    user.authors = json.dumps([a.strip() for a in authors.split(",") if a.strip()])
    user.keywords = json.dumps([k.strip() for k in keywords.split(",") if k.strip()])
    if confirm_reset:
        user.feedback_history = '[]'
    db.commit()
    
    # Очищаем сессию пользователя при смене настроек
    session_key = f"user_{user.id}"
    if session_key in user_sessions:
        del user_sessions[session_key]
    
    return RedirectResponse(url="/dashboard", status_code=303)

# ============ API ============

@app.post("/rate_article")
async def rate_article(request: Request, article_id: str = Form(...), rating: str = Form(...),
                       title: str = Form(""), authors: str = Form(""), abstract: str = Form(""),
                       url: str = Form(""), topic_id: int = Form(0), user_id: Optional[str] = Cookie(None),
                       db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401)
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404)
    
    article = db.query(Article).filter(Article.arxiv_id == article_id).first()
    if not article:
        article = Article(arxiv_id=article_id, title=title, authors=authors, abstract=abstract,
                         url=url, topic_id=topic_id if topic_id > 0 else None,
                         published_date=datetime.utcnow(), is_new=True, discovered_at=datetime.utcnow())
        db.add(article)
        db.commit()
        db.refresh(article)
    
    if rating == 'remove':
        db.query(ArticleRating).filter(ArticleRating.user_id == user.id, ArticleRating.article_id == article.id).delete()
        db.commit()
        history = json.loads(user.feedback_history) if user.feedback_history else []
        history = [h for h in history if h.get('article_id') != article.id]
        user.feedback_history = json.dumps(history)
        db.commit()
        return JSONResponse({"status": "success", "rating": None})
    
    existing = db.query(ArticleRating).filter(ArticleRating.user_id == user.id, ArticleRating.article_id == article.id).first()
    if existing:
        existing.rating = rating
        existing.created_at = datetime.utcnow()
    else:
        new_rating = ArticleRating(user_id=user.id, article_id=article.id, rating=rating)
        db.add(new_rating)
    db.commit()
    
    # ОБУЧАЕМ НЕЙРОСЕТЬ
    neural_engine.update_from_feedback(user, article, rating)
    
    # Обновляем сессию пользователя
    session_key = f"user_{user.id}"
    if session_key in user_sessions:
        for a in user_sessions[session_key]:
            if a['arxiv_id'] == article_id:
                a['user_rating'] = rating
                break
    
    # ПОСЛЕ КАЖДОЙ ОЦЕНКИ - ПЕРЕСЧИТЫВАЕМ ОСТАВШИЕСЯ СТАТЬИ
    current_articles = user_sessions.get(session_key, [])
    rated_ids = set()
    ratings_db = db.query(ArticleRating).filter(ArticleRating.user_id == user.id).all()
    for r in ratings_db:
        if r.article:
            rated_ids.add(r.article.arxiv_id)
    
    unrated_articles = [a for a in current_articles if a['arxiv_id'] not in rated_ids]
    
    # Если осталось мало неоцененных статей (< 5), загружаем новые
    if len(unrated_articles) < 5:
        logger.info(f"🔄 Осталось {len(unrated_articles)} неоцененных статей, загружаем новые...")
        
        # Отправляем WebSocket уведомление о скором обновлении
        await ws_manager.send_personal_message(user.id, {'type': 'preparing_refresh', 'message': 'Нейросеть готовит новые рекомендации...'})
        
        # Получаем новые рекомендации с учетом обновленных предпочтений
        new_articles = await get_fresh_recommendations(user, db, limit=15)
        
        # Обновляем сессию
        user_sessions[session_key] = new_articles
        
        # Отправляем WebSocket уведомление о необходимости обновить страницу
        await ws_manager.send_personal_message(user.id, {'type': 'refresh_needed', 'message': 'Новые статьи готовы! Обновите страницу.'})
        
        return JSONResponse({
            "status": "success", 
            "rating": rating,
            "refresh_needed": True,
            "message": "Нейросеть обновила рекомендации!"
        })
    
    # Пересчитываем рейтинг оставшихся статей на основе новой оценки
    if len(unrated_articles) > 0:
        article_objects = []
        for a in unrated_articles:
            art = db.query(Article).filter(Article.arxiv_id == a['arxiv_id']).first()
            if art:
                article_objects.append(art)
        
        if article_objects:
            arxiv_parser = ArxivDirectParser(db)
            reranked = neural_engine.rerank_articles(user, article_objects, arxiv_parser)
            
            new_order = []
            for art in reranked:
                for a in unrated_articles:
                    if a['arxiv_id'] == art.arxiv_id:
                        new_order.append(a)
                        break
            
            rated_articles = [a for a in current_articles if a['arxiv_id'] in rated_ids]
            user_sessions[session_key] = rated_articles + new_order
    
    return JSONResponse({"status": "success", "rating": rating})

@app.post("/api/detailed-feedback")
async def detailed_feedback(
    request: Request,
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """Принимает детальную обратную связь и обучает нейросеть"""
    if not user_id:
        raise HTTPException(status_code=401)
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404)
    
    data = await request.json()
    
    accuracy = data.get('accuracy', 0)
    relevance = data.get('relevance', 0)
    freshness = data.get('freshness', 0)
    feedback_text = data.get('feedback_text', '')
    article_ids = data.get('article_ids', [])
    
    # Сохраняем обратную связь в историю пользователя
    history = json.loads(user.feedback_history) if user.feedback_history else []
    
    feedback_entry = {
        'type': 'batch_feedback',
        'accuracy': accuracy,
        'relevance': relevance,
        'freshness': freshness,
        'feedback_text': feedback_text,
        'article_ids': article_ids,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    history.append(feedback_entry)
    
    if len(history) > 500:
        history = history[-500:]
    
    user.feedback_history = json.dumps(history)
    
    # Если есть текстовые пожелания, извлекаем ключевые слова и авторов
    if feedback_text:
        import re
        potential_authors = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', feedback_text)
        tech_keywords = re.findall(r'\b(?:deep learning|machine learning|neural network|AI|NLP|computer vision|robotics|reinforcement learning|GAN|transformer|LLM|GPT|BERT)\b', feedback_text, re.IGNORECASE)
        
        current_authors = json.loads(user.authors) if user.authors and user.authors != '[]' else []
        current_keywords = json.loads(user.keywords) if user.keywords and user.keywords != '[]' else []
        
        for author in potential_authors:
            if len(author) > 3 and author not in current_authors:
                current_authors.append(author)
        
        for kw in tech_keywords:
            if kw.lower() not in [k.lower() for k in current_keywords]:
                current_keywords.append(kw)
        
        user.authors = json.dumps(current_authors[:30])
        user.keywords = json.dumps(current_keywords[:30])
    
    db.commit()
    
    logger.info(f"Detailed feedback from user {user.id}: avg_rating={(accuracy+relevance+freshness)/3:.1f}")
    
    return JSONResponse({
        "status": "success",
        "message": "Feedback saved"
    })

@app.get("/api/live-articles")
async def get_live_articles(user_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """Получение новой порции статей с переранжированием на основе оценок"""
    if not user_id:
        return JSONResponse({"articles": [], "error": "No user_id"})
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return JSONResponse({"articles": [], "error": "User not found"})
    
    user_topics = [t for t in user.topics] if user.topics else []
    
    if not user_topics:
        return JSONResponse({"articles": [], "message": "No topics selected"})
    
    logger.info(f"🔄 Загрузка новых персонализированных статей для user {user.id}")
    
    arxiv_parser = ArxivDirectParser(db)
    
    # ОЧИЩАЕМ КЭШ показанных статей перед загрузкой новых
    arxiv_parser.clear_cache(user.id)
    
    # Получаем свежие рекомендации
    articles_data = await get_fresh_recommendations(user, db, limit=15)
    
    # Обновляем сессию
    session_key = f"user_{user.id}"
    user_sessions[session_key] = articles_data
    
    return JSONResponse({"articles": articles_data})

@app.get("/api/profile")
async def get_profile(user_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401)
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404)
    
    history = json.loads(user.feedback_history) if user.feedback_history else []
    likes = len([h for h in history if h.get('rating') == 'like'])
    dislikes = len([h for h in history if h.get('rating') == 'dislike'])
    
    db_likes = db.query(ArticleRating).filter(ArticleRating.user_id == user.id, ArticleRating.rating == 'like').count()
    db_dislikes = db.query(ArticleRating).filter(ArticleRating.user_id == user.id, ArticleRating.rating == 'dislike').count()
    likes = max(likes, db_likes)
    dislikes = max(dislikes, db_dislikes)
    
    total_ratings = likes + dislikes
    accuracy = likes / total_ratings if total_ratings > 0 else 0
    total_articles = db.query(Article).count()
    
    # Получаем данные из НАСТРОЕК пользователя
    user_topics = [t.name for t in user.topics] if user.topics else []
    user_authors = json.loads(user.authors) if user.authors and user.authors != '[]' else []
    user_keywords = json.loads(user.keywords) if user.keywords and user.keywords != '[]' else []
    
    return JSONResponse({
        "likes": likes, 
        "dislikes": dislikes, 
        "total_ratings": total_ratings,
        "total_articles": total_articles, 
        "accuracy": accuracy,
        "user_topics": user_topics,
        "user_authors": user_authors,
        "user_keywords": user_keywords
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)