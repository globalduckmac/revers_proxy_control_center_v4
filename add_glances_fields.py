"""
Скрипт для добавления полей интеграции с Glances в таблицу Server

Для запуска:
python add_glances_fields.py
"""

import logging
from app import app, db
from datetime import datetime
from sqlalchemy import text

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_glances_fields():
    """
    Добавляет поля для интеграции с Glances в таблицу Server.
    """
    try:
        # Используем контекст приложения Flask для доступа к базе данных
        with app.app_context():
            # Выполняем SQL-запросы для добавления новых полей
            logger.info("Начинаем добавление полей для Glances в таблицу server")
            
            # Проверяем, существуют ли уже эти поля
            columns = db.session.execute(
                text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'server' AND column_name LIKE 'glances_%'
                """)
            ).fetchall()
            
            existing_columns = [col[0] for col in columns]
            logger.info(f"Существующие колонки Glances: {existing_columns}")
            
            # Добавляем только те поля, которых еще нет
            add_columns = []
            
            if 'glances_enabled' not in existing_columns:
                add_columns.append("ADD COLUMN glances_enabled BOOLEAN DEFAULT FALSE")
            
            if 'glances_installed' not in existing_columns:
                add_columns.append("ADD COLUMN glances_installed BOOLEAN DEFAULT FALSE")
            
            if 'glances_port' not in existing_columns:
                add_columns.append("ADD COLUMN glances_port INTEGER DEFAULT 61208")
            
            if 'glances_web_port' not in existing_columns:
                add_columns.append("ADD COLUMN glances_web_port INTEGER DEFAULT 61209")
            
            if 'glances_status' not in existing_columns:
                add_columns.append("ADD COLUMN glances_status VARCHAR(20) DEFAULT 'not_installed'")
            
            if 'glances_last_check' not in existing_columns:
                add_columns.append("ADD COLUMN glances_last_check TIMESTAMP WITHOUT TIME ZONE")
            
            # Проверяем, есть ли колонки для добавления
            if not add_columns:
                logger.info("Все необходимые поля уже существуют в таблице server")
                return True
            
            # Формируем запрос ALTER TABLE
            alter_query = f"ALTER TABLE server {', '.join(add_columns)}"
            logger.info(f"Выполняем запрос: {alter_query}")
            
            # Выполняем запрос
            db.session.execute(text(alter_query))
            db.session.commit()
            
            logger.info("Поля для Glances успешно добавлены в таблицу server")
            
            # Проверяем, что поля добавились
            columns_after = db.session.execute(
                text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'server' AND column_name LIKE 'glances_%'
                """)
            ).fetchall()
            
            existing_columns_after = [col[0] for col in columns_after]
            logger.info(f"Колонки Glances после миграции: {existing_columns_after}")
            
            return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении полей для Glances: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Запуск скрипта добавления полей Glances")
    success = add_glances_fields()
    if success:
        logger.info("Скрипт успешно выполнен")
    else:
        logger.error("Скрипт завершился с ошибкой")