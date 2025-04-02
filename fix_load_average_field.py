#!/usr/bin/env python
"""
Скрипт для изменения длины поля load_average в таблице server_metric

Для запуска:
python fix_load_average_field.py
"""

import logging
import sys
import os
from sqlalchemy import text

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fix_load_average_field():
    """
    Изменяет длину поля load_average в таблице server_metric с 30 до 100 символов
    """
    from app import app, db
    
    try:
        # Получаем URL для подключения к БД
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        logger.info(f"Подключение к базе данных...")
        
        # Выполнение SQL-запроса для изменения типа колонки
        with app.app_context():
            # Выполняем SQL-запрос напрямую через connection объект
            sql = text("ALTER TABLE server_metric ALTER COLUMN load_average TYPE VARCHAR(100)")
            db.session.execute(sql)
            db.session.commit()
            
            logger.info("Длина поля load_average успешно изменена с 30 до 100 символов")
            return True
            
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return False
        
if __name__ == "__main__":
    logger.info("Запуск скрипта изменения длины поля load_average...")
    
    try:
        if fix_load_average_field():
            logger.info("Скрипт успешно выполнен")
            sys.exit(0)
        else:
            logger.error("Ошибка выполнения скрипта")
            sys.exit(1)
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}")
        sys.exit(1)