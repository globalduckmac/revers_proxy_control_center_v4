# -*- coding: utf-8 -*-

"""
Скрипт для добавления таблиц ExternalServer и ExternalServerMetric в базу данных

Для запуска:
python add_external_server_table.py
"""

import logging
import os
import sys
from datetime import datetime

# Добавляем текущую директорию в путь импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем необходимые модули
from app import db, app
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.sql import text

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_external_server_tables():
    """
    Добавляет таблицы external_server и external_server_metric в базу данных.
    """
    # Проверка существования таблицы external_server
    with app.app_context():
        try:
            # Проверяем, существует ли таблица external_server
            result = db.session.execute(text("SELECT to_regclass('public.external_server');")).scalar()
            if result:
                logger.info("Таблица external_server уже существует.")
            else:
                # Создаем таблицу external_server
                db.session.execute(text("""
                    CREATE TABLE external_server (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        ip_address VARCHAR(255) NOT NULL,
                        description TEXT,
                        glances_port INTEGER DEFAULT 61208,
                        is_active BOOLEAN DEFAULT TRUE,
                        last_check TIMESTAMP WITHOUT TIME ZONE,
                        last_status VARCHAR(50),
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """))
                logger.info("Таблица external_server успешно создана.")
            
            # Проверяем, существует ли таблица external_server_metric
            result = db.session.execute(text("SELECT to_regclass('public.external_server_metric');")).scalar()
            if result:
                logger.info("Таблица external_server_metric уже существует.")
            else:
                # Создаем таблицу external_server_metric
                db.session.execute(text("""
                    CREATE TABLE external_server_metric (
                        id SERIAL PRIMARY KEY,
                        external_server_id INTEGER NOT NULL,
                        metric_type VARCHAR(50) NOT NULL,
                        metric_name VARCHAR(50) NOT NULL,
                        metric_value TEXT NOT NULL,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (external_server_id) REFERENCES external_server(id) ON DELETE CASCADE
                    );
                """))
                logger.info("Таблица external_server_metric успешно создана.")
            
            # Подтверждаем изменения
            db.session.commit()
            logger.info("Все таблицы для внешних серверов успешно созданы.")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при создании таблиц: {str(e)}")
            raise

# Основная функция
if __name__ == "__main__":
    logger.info("Начало добавления таблиц для внешних серверов...")
    add_external_server_tables()
    logger.info("Добавление таблиц для внешних серверов завершено.")