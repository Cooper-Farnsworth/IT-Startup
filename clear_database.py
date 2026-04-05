#!/usr/bin/env python
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, User, Topic, Article, ArticleRating, UserVector, BatchRating, Notification, Base, engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_database():
    """Полная очистка базы данных"""
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
        response = input("\n⚠️  ВНИМАНИЕ! Это удалит ВСЕ данные из БД!\nВведите 'YES' для подтверждения: ")
        
        if response != 'YES':
            logger.info("❌ Очистка отменена")
            return
        
        logger.info("\n🗑️  Начинаем очистку...")
        
        # Удаляем данные в правильном порядке (сначала связанные данные)
        
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
        
        # 5. Удаляем статьи
        articles_count = db.query(Article).delete()
        logger.info(f"   ✅ Удалено статей: {articles_count}")
        
        # 6. Очищаем связи пользователей с темами
        db.execute("DELETE FROM user_topics")
        logger.info(f"   ✅ Очищены связи пользователей с темами")
        
        # 7. Удаляем темы
        topics_count = db.query(Topic).delete()
        logger.info(f"   ✅ Удалено тем: {topics_count}")
        
        # 8. Удаляем пользователей
        users_count = db.query(User).delete()
        logger.info(f"   ✅ Удалено пользователей: {users_count}")
        
        # Сохраняем изменения
        db.commit()
        
        logger.info("\n" + "=" * 50)
        logger.info("✅ БАЗА ДАННЫХ ПОЛНОСТЬЮ ОЧИЩЕНА!")
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

def drop_and_recreate_tables():
    """Полностью пересоздает таблицы (более радикальный метод)"""
    
    response = input("\n⚠️  УДАЛИТЬ И ПЕРЕСОЗДАТЬ ВСЕ ТАБЛИЦЫ?\nВведите 'DROP' для подтверждения: ")
    
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
    
    logger.info("\n✅ БАЗА ДАННЫХ ПЕРЕСОЗДАНА!")

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🧹 ИНСТРУМЕНТ ОЧИСТКИ БАЗЫ ДАННЫХ")
    print("=" * 50)
    print("\nВыберите действие:")
    print("1. Очистить данные (сохранить структуру)")
    print("2. Полностью удалить и пересоздать таблицы")
    print("3. Выйти")
    
    choice = input("\nВаш выбор (1/2/3): ")
    
    if choice == '1':
        clear_database()
    elif choice == '2':
        drop_and_recreate_tables()
    else:
        print("Выход...")