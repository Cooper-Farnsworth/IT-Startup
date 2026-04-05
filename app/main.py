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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Импорты
from app.database import (
    SessionLocal, User, Topic, Article, ArticleRating, 
    BatchRating, Notification, init_db
)
from app.neural_engine import neural_engine
from app.websocket_manager import ws_manager
from app.arxiv_fetcher import ArxivFetcher

# Инициализация FastAPI
app = FastAPI(title="Science Distributor - Real Articles from arXiv")

# Создаем директорию для статических файлов
os.makedirs("app/static", exist_ok=True)

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="app/static"))

templates = Jinja2Templates(directory="app/templates")

# Аутентификация
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
async def startup_event():
    """Запуск при инициализации - загружаем реальные статьи"""
    init_db()
    await fetch_real_articles_from_arxiv()
    logger.info("Application started with real articles from arXiv!")

async def fetch_real_articles_from_arxiv():
    """Фоновая загрузка реальных статей с arXiv"""
    db = SessionLocal()
    
    try:
        # Проверяем, есть ли уже статьи
        if db.query(Article).count() > 0:
            logger.info(f"Articles already exist: {db.query(Article).count()} articles")
            return
        
        # Создаем темы, если их нет
        if db.query(Topic).count() == 0:
            topics_data = [
                ("Artificial Intelligence", "cs.AI"),
                ("Machine Learning", "cs.LG"),
                ("Natural Language Processing", "cs.CL"),
                ("Computer Vision", "cs.CV"),
                ("Physics", "physics"),
                ("Mathematics", "math"),
                ("Biology", "q-bio")
            ]
            
            for topic_name, arxiv_cat in topics_data:
                topic = Topic(name=topic_name, arxiv_category=arxiv_cat)
                db.add(topic)
            
            db.commit()
            logger.info("Topics created")
        
        # Загружаем статьи для каждой темы
        fetcher = ArxivFetcher(db)
        
        # Категории для загрузки
        categories_to_fetch = [
            ("cs.AI", "Artificial Intelligence"),
            ("cs.LG", "Machine Learning"),
            ("cs.CL", "Natural Language Processing"),
            ("cs.CV", "Computer Vision"),
            ("physics", "Physics")
        ]
        
        total_saved = 0
        
        for arxiv_cat, topic_name in categories_to_fetch:
            topic = db.query(Topic).filter(Topic.name == topic_name).first()
            if not topic:
                continue
            
            logger.info(f"Fetching articles for {topic_name} from category {arxiv_cat}")
            
            # Получаем реальные статьи
            articles = fetcher.fetch_real_articles(category=arxiv_cat, max_results=30)
            
            # Сохраняем в БД
            saved = fetcher.save_articles_to_db(articles, topic.id)
            total_saved += saved
            
            # Небольшая задержка между запросами
            await asyncio.sleep(2)
        
        logger.info(f"Initial fetch complete! Total new articles: {total_saved}")
        
    except Exception as e:
        logger.error(f"Error fetching articles: {e}")
    finally:
        db.close()

# WebSocket endpoint
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await ws_manager.connect(user_id, websocket)
    
    try:
        await websocket.send_json({
            'type': 'connected',
            'message': 'Connected to real-time updates'
        })
        
        while True:
            data = await websocket.receive_text()
            if data == 'ping':
                await websocket.send_text('pong')
                
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id)

# Auth routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Email already registered"
        })
    
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
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not pwd_context.verify(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid credentials"
        })
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id))
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not user_id:
        return RedirectResponse(url="/login")
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login")
    
    # Получаем темы пользователя
    user_topics = [t for t in user.topics] if user.topics else []
    
    if not user_topics:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user": user,
            "articles": [],
            "user_ratings": {},
            "ws_url": f"ws://localhost:8000/ws/{user.id}",
            "no_articles_message": "Пожалуйста, выберите темы в настройках",
            "total_rated": 0
        })
    
    # Получаем ID уже оценённых статей пользователя
    rated_arxiv_ids = set()
    ratings = db.query(ArticleRating).join(Article).filter(
        ArticleRating.user_id == user.id
    ).all()
    
    # Сохраняем оценки в словарь
    user_ratings_dict = {}
    for rating in ratings:
        if rating.article and rating.article.arxiv_id:
            rated_arxiv_ids.add(rating.article.arxiv_id)
            user_ratings_dict[rating.article.arxiv_id] = rating.rating
    
    logger.info(f"User {user.id} has rated {len(rated_arxiv_ids)} articles")
    
    # Загружаем свежие статьи с arXiv
    fetcher = ArxivFetcher(db)
    candidate_articles = []
    
    # ВАЖНО: Определяем seen_ids ДО цикла
    seen_ids = set()
    
    for topic in user_topics:
        if topic.arxiv_category:
            # Пропускаем нерабочие категории
            if topic.arxiv_category == "cs":
                logger.warning(f"Skipping invalid category: {topic.arxiv_category}")
                continue
                
            logger.info(f"Fetching articles for {topic.name}...")
            try:
                articles = fetcher.fetch_real_articles(
                    category=topic.arxiv_category, 
                    max_results=50
                )
                
                for article in articles:
                    arxiv_id = article.get('arxiv_id')
                    
                    if not arxiv_id:
                        continue
                    
                    # Пропускаем уже оценённые
                    if arxiv_id in rated_arxiv_ids:
                        continue
                    
                    # Пропускаем дубликаты в текущей загрузке
                    if arxiv_id in seen_ids:
                        continue
                    
                    seen_ids.add(arxiv_id)
                    
                    # Сохраняем или получаем статью из БД
                    db_article = db.query(Article).filter(Article.arxiv_id == arxiv_id).first()
                    if not db_article:
                        db_article = Article(
                            arxiv_id=arxiv_id,
                            title=article.get('title', ''),
                            authors=article.get('authors', ''),
                            abstract=article.get('abstract', ''),
                            url=article.get('url', ''),
                            topic_id=topic.id,
                            published_date=article.get('published_date', datetime.utcnow()),
                            is_new=True,
                            discovered_at=datetime.utcnow()
                        )
                        db.add(db_article)
                        db.commit()
                        db.refresh(db_article)
                    
                    candidate_articles.append(db_article)
            except Exception as e:
                logger.error(f"Error fetching from {topic.name}: {e}")
                continue
    
    # Используем нейросеть для персонализации
    if candidate_articles:
        try:
            personalized_articles = neural_engine.get_personalized_articles(
                user, 
                candidate_articles, 
                limit=15
            )
            
            if len(personalized_articles) < 15 and len(candidate_articles) > len(personalized_articles):
                remaining = [a for a in candidate_articles if a not in personalized_articles]
                import random
                needed = 15 - len(personalized_articles)
                personalized_articles.extend(random.sample(remaining, min(needed, len(remaining))))
            
            # Используем нейросеть для персонализации
            if candidate_articles:
                try:
                    personalized_articles = neural_engine.get_personalized_articles(
                        user, 
                        candidate_articles, 
                        limit=15  # Здесь уже 15
                    )
                    
                    # Если нейросеть вернула меньше 15, добавляем случайные
                    if len(personalized_articles) < 15 and len(candidate_articles) > len(personalized_articles):
                        remaining = [a for a in candidate_articles if a not in personalized_articles]
                        import random
                        needed = 15 - len(personalized_articles)
                        personalized_articles.extend(random.sample(remaining, min(needed, len(remaining))))
                    
                    articles = personalized_articles[:15]  # Добавьте это ограничение
                except Exception as e:
                    logger.error(f"Error in personalization: {e}")
                    articles = candidate_articles[:15]  # Здесь уже 15
            else:
                articles = []
        except Exception as e:
            logger.error(f"Error in personalization: {e}")
            articles = candidate_articles[:15]
    else:
        articles = []
    
    # Преобразуем для шаблона
    articles_data = []
    for article in articles:
        articles_data.append({
            'arxiv_id': article.arxiv_id,
            'title': article.title,
            'authors': article.authors,
            'abstract': (article.abstract[:400] if article.abstract else ''),
            'url': article.url,
            'topic_id': article.topic_id,
            'topic_name': article.topic.name if article.topic else 'Unknown',
            'user_rating': user_ratings_dict.get(article.arxiv_id)
        })
    
    logger.info(f"Dashboard: Showing {len(articles_data)} personalized articles for user {user.id}")
    
    articles_data = articles_data[:15]

    logger.info(f"Dashboard: Showing {len(articles_data)} personalized articles for user {user.id}")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "articles": articles_data,
        "user_ratings": user_ratings_dict,
        "ws_url": f"ws://localhost:8000/ws/{user.id}",
        "live_mode": True,
        "total_rated": len(rated_arxiv_ids)
    })

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
    
    # Добавляем детальную обратную связь
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
    
    # Ограничиваем историю
    if len(history) > 500:
        history = history[-500:]
    
    user.feedback_history = json.dumps(history)
    
    # Если есть текстовые пожелания, извлекаем ключевые слова и авторов
    if feedback_text:
        import re
        # Извлекаем потенциальных авторов (с заглавной буквы)
        potential_authors = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', feedback_text)
        # Извлекаем ключевые слова (технические термины)
        tech_keywords = re.findall(r'\b(?:deep learning|machine learning|neural network|AI|NLP|computer vision|robotics|reinforcement learning|GAN|transformer|LLM|GPT|BERT)\b', feedback_text, re.IGNORECASE)
        
        # Обновляем предпочтения пользователя
        current_authors = json.loads(user.authors) if user.authors and user.authors != '[]' else []
        current_keywords = json.loads(user.keywords) if user.keywords and user.keywords != '[]' else []
        
        # Добавляем новых авторов
        for author in potential_authors:
            if len(author) > 3 and author not in current_authors:
                current_authors.append(author)
        
        # Добавляем новые ключевые слова
        for kw in tech_keywords:
            if kw.lower() not in [k.lower() for k in current_keywords]:
                current_keywords.append(kw)
        
        user.authors = json.dumps(current_authors)
        user.keywords = json.dumps(current_keywords)
        
        logger.info(f"Updated user preferences from feedback: authors={current_authors}, keywords={current_keywords}")
    
    # Если оценка подборки низкая, уменьшаем вес exploration
    avg_rating = (accuracy + relevance + freshness) / 3 if (accuracy + relevance + freshness) > 0 else 0
    
    db.commit()
    
    logger.info(f"Detailed feedback from user {user.id}: avg_rating={avg_rating}, text_length={len(feedback_text)}")
    
    return JSONResponse({
        "status": "success",
        "message": "Feedback saved",
        "avg_rating": avg_rating
    })

@app.post("/rate_article")
async def rate_article(
    request: Request,
    article_id: str = Form(...),
    rating: str = Form(...),
    title: str = Form(""),
    authors: str = Form(""),
    abstract: str = Form(""),
    url: str = Form(""),
    topic_id: int = Form(0),
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not user_id:
        raise HTTPException(status_code=401)
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404)
    
    # Ищем статью в БД по arxiv_id
    article = db.query(Article).filter(Article.arxiv_id == article_id).first()
    
    # Если статьи нет в БД - создаём её
    if not article:
        article = Article(
            arxiv_id=article_id,
            title=title,
            authors=authors,
            abstract=abstract,
            url=url,
            topic_id=topic_id if topic_id > 0 else None,
            published_date=datetime.utcnow(),
            is_new=True,
            discovered_at=datetime.utcnow()
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        logger.info(f"Created new article in DB: {article_id}")
    
    # Если rating == 'remove', удаляем оценку
    if rating == 'remove':
        db.query(ArticleRating).filter(
            ArticleRating.user_id == user.id,
            ArticleRating.article_id == article.id
        ).delete()
        db.commit()
        
        # Обновляем нейросеть (удаляем из истории)
        history = json.loads(user.feedback_history) if user.feedback_history else []
        history = [h for h in history if h.get('article_id') != article.id]
        user.feedback_history = json.dumps(history)
        db.commit()
        
        logger.info(f"User {user.id} removed rating for article {article_id}")
        return JSONResponse({"status": "success", "rating": None})
    
    # Сохраняем оценку
    existing = db.query(ArticleRating).filter(
        ArticleRating.user_id == user.id,
        ArticleRating.article_id == article.id
    ).first()
    
    if existing:
        existing.rating = rating
        existing.created_at = datetime.utcnow()
    else:
        new_rating = ArticleRating(
            user_id=user.id, 
            article_id=article.id, 
            rating=rating
        )
        db.add(new_rating)
    
    db.commit()
    
    # ОБУЧАЕМ НЕЙРОСЕТЬ на основе новой оценки
    neural_engine.update_from_feedback(user, article, rating)
    
    logger.info(f"User {user.id} rated article {article_id} as {rating} - нейросеть обновлена")
    
    return JSONResponse({"status": "success", "rating": rating})

@app.get("/api/live-articles")
async def get_live_articles(
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """API для получения свежих статей с arXiv"""
    try:
        if not user_id:
            return JSONResponse({"articles": [], "error": "No user_id"})
        
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            return JSONResponse({"articles": [], "error": "User not found"})
        
        user_topics = [t for t in user.topics] if user.topics else []
        
        if not user_topics:
            return JSONResponse({"articles": [], "message": "No topics selected"})
        
        # Получаем ID уже оценённых статей пользователя
        rated_arxiv_ids = set()
        ratings = db.query(ArticleRating).join(Article).filter(
            ArticleRating.user_id == user.id
        ).all()
        
        for rating in ratings:
            if rating.article and rating.article.arxiv_id:
                rated_arxiv_ids.add(rating.article.arxiv_id)
        
        logger.info(f"User {user.id} has rated {len(rated_arxiv_ids)} articles")
        
        fetcher = ArxivFetcher(db)
        all_articles = []
        seen_ids = set()
        
        # Загружаем статьи со всех тем без ограничений
        for topic in user_topics:  # Убрано ограничение [:3]
            if topic.arxiv_category:
                logger.info(f"Fetching articles for {topic.name}...")
                try:
                    # Увеличиваем max_results до 100 для большего количества статей
                    arxiv_articles = fetcher.fetch_real_articles(
                        category=topic.arxiv_category,
                        max_results=100  # Увеличено до 100
                    )
                    
                    logger.info(f"Fetched {len(arxiv_articles)} articles from {topic.name}")
                    
                    for a in arxiv_articles:
                        arxiv_id = a.get('arxiv_id')
                        
                        if not arxiv_id:
                            continue
                        
                        # Пропускаем уже оценённые статьи
                        if arxiv_id in rated_arxiv_ids:
                            continue
                        
                        if arxiv_id in seen_ids:
                            continue
                        
                        seen_ids.add(arxiv_id)
                        
                        all_articles.append({
                            'arxiv_id': arxiv_id,
                            'title': a.get('title', 'No title'),
                            'authors': a.get('authors', 'Unknown'),
                            'abstract': a.get('abstract', '')[:400],
                            'url': a.get('url', '#'),
                            'topic_id': topic.id,
                            'topic_name': topic.name
                        })
                except Exception as e:
                    logger.error(f"Error fetching from {topic.name}: {e}")
                    continue
        
        # Перемешиваем
        random.shuffle(all_articles)
        
        # Возвращаем ВСЕ найденные статьи (без ограничения 20)
        result_articles = all_articles  # Убрано [:20]
        
        logger.info(f"Returning {len(result_articles)} new articles (skipped {len(rated_arxiv_ids)} rated)")
        
        if len(result_articles) == 0:
            return JSONResponse({"articles": [], "message": "Нет новых статей. Попробуйте добавить больше тем в настройках."})
        
        return JSONResponse({"articles": result_articles})
        
    except Exception as e:
        logger.error(f"Error in get_live_articles: {e}")
        return JSONResponse({"articles": [], "error": str(e)})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not user_id:
        return RedirectResponse(url="/login")
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    topics = db.query(Topic).all()
    user_topics = [t.id for t in user.topics] if user.topics else []
    
    # Загружаем авторов и ключевые слова
    user_authors = ", ".join(json.loads(user.authors)) if user.authors and user.authors != '[]' else ""
    user_keywords = ", ".join(json.loads(user.keywords)) if user.keywords and user.keywords != '[]' else ""
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user,
        "topics": topics,
        "user_topics": user_topics,
        "user_authors": user_authors,
        "user_keywords": user_keywords
    })

@app.post("/settings")
async def save_settings(
    request: Request,
    topics: List[int] = Form([]),
    authors: str = Form(""),
    keywords: str = Form(""),
    confirm_reset: Optional[str] = Form(None),
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not user_id:
        return RedirectResponse(url="/login")
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    
    # Проверяем смену тем
    old_topics = set([t.id for t in user.topics])
    new_topics = set(topics)
    
    if old_topics != new_topics and not confirm_reset:
        return JSONResponse({
            "warning": "Смена темы приведёт к сбросу данных обучения",
            "needs_confirmation": True
        })
    
    # Обновляем темы
    user.topics = []
    for topic_id in topics:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if topic:
            user.topics.append(topic)
    
    # Сохраняем авторов и ключевые слова
    authors_list = [a.strip() for a in authors.split(",") if a.strip()]
    keywords_list = [k.strip() for k in keywords.split(",") if k.strip()]
    
    user.authors = json.dumps(authors_list)
    user.keywords = json.dumps(keywords_list)
    
    # Сбрасываем историю при подтвержденной смене
    if confirm_reset:
        user.feedback_history = '[]'
    
    db.commit()
    
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("user_id")
    return response

@app.get("/api/refresh-articles")
async def refresh_articles(
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """Ручное обновление статей"""
    if not user_id:
        raise HTTPException(status_code=401)
    
    # Запускаем фоновую загрузку
    asyncio.create_task(fetch_real_articles_from_arxiv())
    
    return JSONResponse({"status": "success", "message": "Article refresh started"})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not user_id:
        return RedirectResponse(url="/login")
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login")
    
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

@app.get("/api/profile")
async def get_profile(
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not user_id:
        raise HTTPException(status_code=401)
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404)
    
    # Принудительно обновляем сессию
    db.refresh(user)
    
    # Анализируем историю
    history = json.loads(user.feedback_history) if user.feedback_history else []
    
    # Подсчитываем лайки и дизлайки из истории
    likes = 0
    dislikes = 0
    for h in history:
        rating = h.get('rating')
        if rating == 'like':
            likes += 1
        elif rating == 'dislike':
            dislikes += 1
    
    # Также считаем из таблицы ArticleRating (для надёжности)
    db_likes = db.query(ArticleRating).filter(
        ArticleRating.user_id == user.id,
        ArticleRating.rating == 'like'
    ).count()
    
    db_dislikes = db.query(ArticleRating).filter(
        ArticleRating.user_id == user.id,
        ArticleRating.rating == 'dislike'
    ).count()
    
    # Берём максимальные значения
    likes = max(likes, db_likes)
    dislikes = max(dislikes, db_dislikes)
    
    # Топ авторы
    author_counts = {}
    for item in history:
        if item.get('rating') == 'like':
            authors = item.get('authors', [])
            if isinstance(authors, list):
                for author in authors:
                    if author and author.strip():
                        author_counts[author.strip()] = author_counts.get(author.strip(), 0) + 1
            elif isinstance(authors, str) and authors:
                for author in authors.split(','):
                    author = author.strip()
                    if author:
                        author_counts[author] = author_counts.get(author, 0) + 1
    
    top_authors = sorted([{"name": k, "count": v} for k, v in author_counts.items()], 
                        key=lambda x: x['count'], reverse=True)[:10]
    
    # Топ ключевые слова
    keyword_counts = {}
    for item in history:
        if item.get('rating') == 'like':
            keywords = item.get('keywords', [])
            if isinstance(keywords, list):
                for keyword in keywords:
                    if keyword:
                        keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
    
    top_keywords = sorted([{"word": k, "count": v} for k, v in keyword_counts.items()], 
                         key=lambda x: x['count'], reverse=True)[:10]
    
    # Темы
    topic_counts = {}
    for item in history:
        if item.get('rating') == 'like':
            topic = item.get('topic', 'Unknown')
            if topic:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
    
    topics_list = [{"name": k, "count": v} for k, v in topic_counts.items()]
    
    # Точность рекомендаций
    total_ratings = likes + dislikes
    accuracy = likes / total_ratings if total_ratings > 0 else 0
    
    # Общее количество статей в БД
    total_articles = db.query(Article).count()
    
    print(f"Profile stats: likes={likes}, dislikes={dislikes}, total_ratings={total_ratings}, accuracy={accuracy}")
    
    return JSONResponse({
        "likes": likes,
        "dislikes": dislikes,
        "total_ratings": total_ratings,
        "total_articles": total_articles,
        "accuracy": accuracy,
        "top_authors": top_authors,
        "top_keywords": top_keywords,
        "topics": topics_list
    })

@app.post("/api/update-stats")
async def update_stats(
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """Принудительно обновляет статистику пользователя"""
    if not user_id:
        raise HTTPException(status_code=401)
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404)
    
    # Пересчитываем статистику
    history = json.loads(user.feedback_history) if user.feedback_history else []
    
    likes = len([h for h in history if h.get('rating') == 'like'])
    dislikes = len([h for h in history if h.get('rating') == 'dislike'])
    
    # Сохраняем в сессию
    db.commit()
    
    return JSONResponse({
        "status": "success",
        "likes": likes,
        "dislikes": dislikes,
        "total": likes + dislikes
    })

@app.post("/api/refresh-profile")
async def refresh_profile(
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """Принудительное обновление статистики профиля"""
    if not user_id:
        raise HTTPException(status_code=401)
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404)
    
    # Пересчитываем статистику из истории
    history = json.loads(user.feedback_history) if user.feedback_history else []
    
    likes = len([h for h in history if h.get('rating') == 'like'])
    dislikes = len([h for h in history if h.get('rating') == 'dislike'])
    
    return JSONResponse({
        "status": "success",
        "likes": likes,
        "dislikes": dislikes,
        "total_ratings": likes + dislikes
    })

@app.post("/rate_batch")
async def rate_batch(
    rating: int = Form(...),
    user_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """Оценка всей подборки (1-5)"""
    if not user_id:
        raise HTTPException(status_code=401)
    
    batch_rating = BatchRating(user_id=int(user_id), rating=rating)
    db.add(batch_rating)
    db.commit()
    
    return JSONResponse({"status": "success"})

# Функция для уведомления всех пользователей
async def notify_all_users(event_type: str, data: dict):
    """Уведомляет всех активных пользователей через WebSocket"""
    for user_id, websocket in ws_manager.active_connections.items():
        try:
            await websocket.send_json({
                'type': event_type,
                'data': data
            })
        except Exception as e:
            logger.error(f"Error notifying user {user_id}: {e}")

# Периодическая задача для обновления статей
def scheduled_fetch():
    """Плановое обновление статей"""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Автообновление статей...")
    
    db = SessionLocal()
    try:
        fetcher = ArxivFetcher(db)
        total_new = 0
        
        for topic in db.query(Topic).all():
            if topic.arxiv_category:
                articles = fetcher.fetch_real_articles(category=topic.arxiv_category, max_results=20)
                saved = fetcher.save_articles_to_db(articles, topic.id)
                total_new += saved
        
        if total_new > 0:
            print(f"   ✅ Добавлено {total_new} новых статей")
            # ИСПРАВЛЕНО: правильно запускаем асинхронную функцию
            try:
                # Получаем существующий event loop или создаем новый
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Если loop уже запущен, создаем задачу
                    asyncio.create_task(notify_all_users("new_articles", {"count": total_new}))
                else:
                    # Если loop не запущен, запускаем через run_until_complete
                    loop.run_until_complete(notify_all_users("new_articles", {"count": total_new}))
            except RuntimeError:
                # Если нет event loop, создаем новый
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(notify_all_users("new_articles", {"count": total_new}))
        else:
            print(f"   ⚠️ Новых статей не найдено")
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    finally:
        db.close()

# Настройка планировщика
scheduler = BackgroundScheduler()

scheduler.add_job(
    scheduled_fetch,
    trigger=IntervalTrigger(hours=6),  # Каждые 6 часов
    id='scheduled_fetch',
    replace_existing=True
)

# Запуск планировщика при старте приложения
@app.on_event("startup")
async def start_scheduler():
    scheduler.start()
    logger.info("✅ Фоновый планировщик запущен")

# Остановка планировщика при завершении
@app.on_event("shutdown")
async def shutdown_scheduler():
    scheduler.shutdown()
    logger.info("👋 Фоновый планировщик остановлен")