"""
Скрипт для исправления схемы таблицы Domain с помощью прямых SQL-запросов
"""

import logging
from app import app, db
from sqlalchemy import text

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_domain_schema():
    """
    Исправляет схему таблицы domain, добавляя недостающие поля
    """
    with app.app_context():
        try:
            # Проверяем существование колонки previous_ns_status
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'domain' AND column_name = 'previous_ns_status'
            """))
            
            if result.rowcount == 0:
                # Колонка не существует, добавляем её
                db.session.execute(text("""
                    ALTER TABLE domain ADD COLUMN previous_ns_status VARCHAR(20)
                """))
                logger.info("Добавлена колонка previous_ns_status в таблицу domain")
                
                # Устанавливаем начальные значения
                db.session.execute(text("""
                    UPDATE domain SET previous_ns_status = ns_status
                """))
                logger.info("Установлены начальные значения для previous_ns_status")
            else:
                logger.info("Колонка previous_ns_status уже существует в таблице domain")
            
            # Проверяем, нужно ли заполнить NULL значения
            result = db.session.execute(text("""
                SELECT COUNT(*) FROM domain WHERE previous_ns_status IS NULL
            """))
            null_count = result.scalar()
            
            if null_count > 0:
                # Заполняем NULL значения
                db.session.execute(text("""
                    UPDATE domain SET previous_ns_status = ns_status WHERE previous_ns_status IS NULL
                """))
                logger.info(f"Заполнены NULL значения для {null_count} записей в колонке previous_ns_status")
            
            # Сохраняем изменения
            db.session.commit()
            logger.info("Исправление схемы domain выполнено успешно")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при исправлении схемы domain: {str(e)}")
            raise

if __name__ == "__main__":
    logger.info("Запуск исправления схемы domain...")
    fix_domain_schema()
    logger.info("Исправление схемы domain завершено")