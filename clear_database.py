#!/usr/bin/env python
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, User, Topic, Article, ArticleRating, UserVector, BatchRating, Notification, Base, engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_database():
    """Очистка базы данных БЕЗ удаления статей"""
    db = SessionLocal()
    
    try:
        # Получаем статистику перед очисткой
        stats = {
            'users': db.query(User).count(),
            'topics': db.query(Topic).count(),
            'articles': db.query(Article).count(),
            'ratings': db.query(ArticleRating).count(),
            'vectors': db.query(UserVector).count(),
            'batch_ratings': db.query(BatchRating).count(),
            'notifications': db.query(Notification).count()
        }
        
        logger.info("=" * 50)
        logger.info("📊 СТАТИСТИКА ПЕРЕД ОЧИСТКОЙ:")
        for table, count in stats.items():
            logger.info(f"   {table}: {count}")
        logger.info("=" * 50)
        
        # Подтверждение
        response = input("\n⚠️  ВНИМАНИЕ! Это удалит данные пользователей и оценок, но СОХРАНИТ статьи!\nВведите 'YES' для подтверждения: ")
        
        if response != 'YES':
            logger.info("❌ Очистка отменена")
            return
        
        logger.info("\n🗑️  Начинаем очистку (статьи НЕ удаляются)...")
        
        # 1. Удаляем оценки статей
        ratings_count = db.query(ArticleRating).delete()
        logger.info(f"   ✅ Удалено оценок статей: {ratings_count}")
        
        # 2. Удаляем векторы пользователей
        vectors_count = db.query(UserVector).delete()
        logger.info(f"   ✅ Удалено векторов пользователей: {vectors_count}")
        
        # 3. Удаляем оценки подборок
        batch_ratings_count = db.query(BatchRating).delete()
        logger.info(f"   ✅ Удалено оценок подборок: {batch_ratings_count}")
        
        # 4. Удаляем уведомления
        notifications_count = db.query(Notification).delete()
        logger.info(f"   ✅ Удалено уведомлений: {notifications_count}")
        
        # 5. Очищаем связи пользователей с темами (ИСПРАВЛЕНО)
        db.execute(text("DELETE FROM user_topics"))
        logger.info(f"   ✅ Очищены связи пользователей с темами")
        
        # 6. Удаляем пользователей
        users_count = db.query(User).delete()
        logger.info(f"   ✅ Удалено пользователей: {users_count}")
        
        # 7. Удаляем темы (НО НЕ СТАТЬИ!)
        # Сначала очищаем связь статей с темами
        db.query(Article).update({Article.topic_id: None})
        # Затем удаляем темы
        topics_count = db.query(Topic).delete()
        logger.info(f"   ✅ Удалено тем: {topics_count}")
        
        # СТАТЬИ НЕ УДАЛЯЕМ!
        articles_count = db.query(Article).count()
        logger.info(f"   ✅ СТАТЬИ СОХРАНЕНЫ: {articles_count} статей осталось в БД")
        
        # Сохраняем изменения
        db.commit()
        
        logger.info("\n" + "=" * 50)
        logger.info("✅ БАЗА ДАННЫХ ОЧИЩЕНА (СТАТЬИ СОХРАНЕНЫ)!")
        logger.info("=" * 50)
        
        # Показываем финальную статистику
        final_stats = {
            'users': db.query(User).count(),
            'topics': db.query(Topic).count(),
            'articles': db.query(Article).count(),
            'ratings': db.query(ArticleRating).count(),
            'vectors': db.query(UserVector).count(),
        }
        
        logger.info("\n📊 СТАТИСТИКА ПОСЛЕ ОЧИСТКИ:")
        for table, count in final_stats.items():
            logger.info(f"   {table}: {count}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке: {e}")
        db.rollback()
    finally:
        db.close()

def clear_user_data_only():
    """Очищает ТОЛЬКО данные пользователей (сохраняет статьи и темы)"""
    db = SessionLocal()
    
    try:
        stats = {
            'users': db.query(User).count(),
            'ratings': db.query(ArticleRating).count(),
            'vectors': db.query(UserVector).count(),
            'batch_ratings': db.query(BatchRating).count(),
            'notifications': db.query(Notification).count(),
            'articles': db.query(Article).count(),
            'topics': db.query(Topic).count()
        }
        
        logger.info("=" * 50)
        logger.info("📊 ТЕКУЩАЯ СТАТИСТИКА:")
        for table, count in stats.items():
            logger.info(f"   {table}: {count}")
        logger.info("=" * 50)
        
        response = input("\n⚠️  Очистить ТОЛЬКО данные пользователей? (статьи и темы сохранятся)\nВведите 'YES' для подтверждения: ")
        
        if response != 'YES':
            logger.info("❌ Операция отменена")
            return
        
        logger.info("\n🗑️  Очищаем данные пользователей...")
        
        # Удаляем оценки
        ratings_count = db.query(ArticleRating).delete()
        logger.info(f"   ✅ Удалено оценок: {ratings_count}")
        
        # Удаляем векторы
        vectors_count = db.query(UserVector).delete()
        logger.info(f"   ✅ Удалено векторов: {vectors_count}")
        
        # Удаляем оценки подборок
        batch_count = db.query(BatchRating).delete()
        logger.info(f"   ✅ Удалено оценок подборок: {batch_count}")
        
        # Удаляем уведомления
        notifications_count = db.query(Notification).delete()
        logger.info(f"   ✅ Удалено уведомлений: {notifications_count}")
        
        # Очищаем связи (ИСПРАВЛЕНО)
        db.execute(text("DELETE FROM user_topics"))
        logger.info(f"   ✅ Очищены связи пользователей с темами")
        
        # Удаляем пользователей
        users_count = db.query(User).delete()
        logger.info(f"   ✅ Удалено пользователей: {users_count}")
        
        db.commit()
        
        logger.info("\n" + "=" * 50)
        logger.info("✅ ДАННЫЕ ПОЛЬЗОВАТЕЛЕЙ ОЧИЩЕНЫ!")
        logger.info(f"   📚 Статей сохранено: {db.query(Article).count()}")
        logger.info(f"   📁 Тем сохранено: {db.query(Topic).count()}")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

def drop_and_recreate_tables():
    """Полностью пересоздает таблицы (удаляет ВСЕ данные)"""
    
    response = input("\n⚠️  УДАЛИТЬ И ПЕРЕСОЗДАТЬ ВСЕ ТАБЛИЦЫ? (будут удалены ВСЕ данные, включая статьи)\nВведите 'DROP' для подтверждения: ")
    
    if response != 'DROP':
        logger.info("❌ Операция отменена")
        return
    
    logger.info("\n🗑️  Удаляем все таблицы...")
    
    # Удаляем все таблицы
    Base.metadata.drop_all(bind=engine)
    logger.info("   ✅ Все таблицы удалены")
    
    # Создаем таблицы заново
    Base.metadata.create_all(bind=engine)
    logger.info("   ✅ Таблицы созданы заново")
    
    logger.info("\n✅ БАЗА ДАННЫХ ПЕРЕСОЗДАНА (ВСЕ ДАННЫЕ УДАЛЕНЫ)!")

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🧹 ИНСТРУМЕНТ УПРАВЛЕНИЯ БАЗОЙ ДАННЫХ")
    print("=" * 50)
    print("\nВыберите действие:")
    print("1. Очистить данные пользователей (СОХРАНИТЬ статьи и темы)")
    print("2. Полная очистка (СОХРАНИТЬ статьи, удалить темы и пользователей)")
    print("3. Полностью удалить и пересоздать таблицы (УДАЛИТЬ ВСЕ)")
    print("4. Выйти")
    
    choice = input("\nВаш выбор (1/2/3/4): ")
    
    if choice == '1':
        clear_user_data_only()
    elif choice == '2':
        clear_database()
    elif choice == '3':
        drop_and_recreate_tables()
    else:
        print("Выход...")