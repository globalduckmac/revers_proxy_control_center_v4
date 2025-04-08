#!/usr/bin/env python3
"""
Скрипт для добавления поля glances_enabled и переименования поля last_status в status 
в таблице external_server.

Для запуска:
python add_glances_fields_to_external_server.py
"""

import os
import sys
import logging
from sqlalchemy import create_engine, Column, Boolean, inspect, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_glances_fields():
    """
    Добавляет поле glances_enabled в таблицу external_server и
    переименовывает last_status в status, если необходимо.
    """
    # Получаем строку подключения к БД из переменной окружения или используем значение по умолчанию
    db_url = os.environ.get('DATABASE_URL', 'postgresql://rpcc:jidVLxKX5VihdK@localhost/rpcc')
    
    try:
        # Создаем подключение к БД
        engine = create_engine(db_url)
        connection = engine.connect()
        inspector = inspect(engine)
        
        # Проверка существования таблицы
        if not inspector.has_table('external_server'):
            logger.error("Таблица external_server не существует.")
            return False
        
        # Получаем список существующих колонок
        columns = [column['name'] for column in inspector.get_columns('external_server')]
        
        # Проверяем необходимость добавления колонки glances_enabled
        if 'glances_enabled' not in columns:
            logger.info("Добавление колонки glances_enabled в таблицу external_server...")
            connection.execute(text(
                "ALTER TABLE external_server ADD COLUMN glances_enabled BOOLEAN DEFAULT TRUE"
            ))
            logger.info("Колонка glances_enabled успешно добавлена.")
        else:
            logger.info("Колонка glances_enabled уже существует.")
        
        # Проверяем необходимость переименования колонки last_status в status
        if 'last_status' in columns and 'status' not in columns:
            logger.info("Переименование колонки last_status в status...")
            connection.execute(text(
                "ALTER TABLE external_server RENAME COLUMN last_status TO status"
            ))
            logger.info("Колонка last_status успешно переименована в status.")
        elif 'status' in columns:
            logger.info("Колонка status уже существует.")
        
        connection.close()
        return True
    
    except OperationalError as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        return False
    except SQLAlchemyError as e:
        logger.error(f"Ошибка SQLAlchemy при обновлении таблицы: {e}")
        return False
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {e}")
        return False

if __name__ == "__main__":
    logger.info("Запуск скрипта добавления полей в таблицу external_server...")
    if add_glances_fields():
        logger.info("Скрипт успешно выполнен.")
        sys.exit(0)
    else:
        logger.error("Скрипт завершился с ошибкой.")
        sys.exit(1)