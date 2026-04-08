from fastapi import FastAPI, Request, Form, HTTPException, Depends, Cookie, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import Optional, List
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

app = FastAPI(title="Science Distributor - Real Articles from arXiv")
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"))
templates = Jinja2Templates(directory="app/templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Хранилище активных сессий пользователей (текущие статьи)
user_sessions = {}

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
            "no_articles_message": "Пожалуйста, выберите темы в настройках", "total_rated": 0
        })
    
    # Проверяем, есть ли сохраненная сессия для этого пользователя
    session_key = f"user_{user.id}"
    saved_articles = user_sessions.get(session_key)
    
    # Получаем оценки пользователя
    rated_arxiv_ids = set()
    user_ratings_dict = {}
    ratings = db.query(ArticleRating).join(Article).filter(ArticleRating.user_id == user.id).all()
    for rating in ratings:
        if rating.article and rating.article.arxiv_id:
            rated_arxiv_ids.add(rating.article.arxiv_id)
            user_ratings_dict[rating.article.arxiv_id] = rating.rating
    
    # Если есть сохраненная сессия И статьи еще не все оценены - используем её
    if saved_articles and len(saved_articles) > 0:
        # Проверяем, сколько статей из сессии уже оценено
        unrated_count = sum(1 for a in saved_articles if a['arxiv_id'] not in rated_arxiv_ids)
        
        if unrated_count > 0:
            # Используем сохраненные статьи
            articles_data = saved_articles
            logger.info(f"📚 Используем сохраненную сессию: {len(articles_data)} статей, неоценено: {unrated_count}")
            
            return templates.TemplateResponse("dashboard.html", {
                "request": request, "user": user, "articles": articles_data,
                "user_ratings": user_ratings_dict, "ws_url": f"ws://localhost:8000/ws/{user.id}",
                "live_mode": True, "total_rated": len(rated_arxiv_ids)
            })
    
    # Нет сохраненной сессии - загружаем новые статьи
    logger.info(f"🔄 Загрузка новой подборки для user {user.id}")
    
    # Загружаем статьи из БД
    articles_from_db = []
    for topic in user_topics:
        topic_articles = db.query(Article).filter(
            Article.topic_id == topic.id,
            Article.arxiv_id.notin_(rated_arxiv_ids)
        ).order_by(Article.published_date.desc()).limit(100).all()
        articles_from_db.extend(topic_articles)
    
    # Перемешиваем
    random.shuffle(articles_from_db)
    
    # Персонализация
    if articles_from_db:
        try:
            personalized = neural_engine.get_personalized_articles(user, articles_from_db, limit=15)
            articles = personalized
        except:
            articles = articles_from_db[:15]
    else:
        articles = []
    
    articles_data = []
    for article in articles:
        articles_data.append({
            'arxiv_id': article.arxiv_id, 'title': article.title, 'authors': article.authors,
            'abstract': (article.abstract[:400] if article.abstract else ''),
            'url': article.url, 'topic_id': article.topic_id,
            'topic_name': article.topic.name if article.topic else 'Unknown',
            'user_rating': user_ratings_dict.get(article.arxiv_id)
        })
    
    # Сохраняем в сессию
    user_sessions[session_key] = articles_data
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "articles": articles_data,
        "user_ratings": user_ratings_dict, "ws_url": f"ws://localhost:8000/ws/{user.id}",
        "live_mode": True, "total_rated": len(rated_arxiv_ids)
    })

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
    
    neural_engine.update_from_feedback(user, article, rating)
    
    # Обновляем сессию пользователя - помечаем статью как оцененную
    session_key = f"user_{user.id}"
    if session_key in user_sessions:
        for a in user_sessions[session_key]:
            if a['arxiv_id'] == article_id:
                a['user_rating'] = rating
                break
    
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
    """Получение новой порции статей (при нажатии кнопки)"""
    if not user_id:
        return JSONResponse({"articles": [], "error": "No user_id"})
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return JSONResponse({"articles": [], "error": "User not found"})
    
    user_topics = [t for t in user.topics] if user.topics else []
    
    if not user_topics:
        return JSONResponse({"articles": [], "message": "No topics selected"})
    
    # Получаем ID уже оценённых статей
    rated_arxiv_ids = set()
    ratings = db.query(ArticleRating).join(Article).filter(ArticleRating.user_id == user.id).all()
    for rating in ratings:
        if rating.article and rating.article.arxiv_id:
            rated_arxiv_ids.add(rating.article.arxiv_id)
    
    # Загружаем новые статьи (исключая оцененные и показанные в текущей сессии)
    session_key = f"user_{user.id}"
    shown_in_session = set()
    if session_key in user_sessions:
        shown_in_session = {a['arxiv_id'] for a in user_sessions[session_key]}
    
    candidate_articles = []
    for topic in user_topics:
        topic_articles = db.query(Article).filter(
            Article.topic_id == topic.id,
            Article.arxiv_id.notin_(rated_arxiv_ids),
            Article.arxiv_id.notin_(shown_in_session)
        ).order_by(Article.published_date.desc()).limit(100).all()
        candidate_articles.extend(topic_articles)
    
    if not candidate_articles:
        return JSONResponse({"articles": [], "message": "Нет новых статей. Добавьте больше тем в настройках."})
    
    random.shuffle(candidate_articles)
    
    try:
        personalized = neural_engine.get_personalized_articles(user, candidate_articles, limit=15)
        articles = personalized
    except:
        articles = candidate_articles[:15]
    
    articles_data = []
    for article in articles:
        articles_data.append({
            'arxiv_id': article.arxiv_id,
            'title': article.title,
            'authors': article.authors,
            'abstract': (article.abstract[:400] if article.abstract else ''),
            'url': article.url,
            'topic_id': article.topic_id,
            'topic_name': article.topic.name if article.topic else 'Unknown'
        })
    
    # Обновляем сессию новыми статьями
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
    
    return JSONResponse({"likes": likes, "dislikes": dislikes, "total_ratings": total_ratings,
                        "total_articles": total_articles, "accuracy": accuracy})

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

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not user_id:
        return RedirectResponse(url="/login")
    user = db.query(User).filter(User.id == int(user_id)).first()
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)