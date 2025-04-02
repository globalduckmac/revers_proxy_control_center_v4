#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для добавления полей хранения данных биллинга в таблицу Server

Для запуска:
python add_billing_fields.py
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from app import app, db

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_billing_fields():
    """
    Добавляет поля для хранения данных биллинга и комментария в таблицу Server
    """
    try:
        with app.app_context():
            # Проверяем существующие колонки
            inspector = db.inspect(db.engine)
            existing_columns = [column['name'] for column in inspector.get_columns('server')]
            
            # Создаем список полей для добавления
            columns_to_add = []
            
            if 'comment' not in existing_columns:
                columns_to_add.append("comment TEXT")
            
            if 'billing_provider' not in existing_columns:
                columns_to_add.append("billing_provider VARCHAR(128)")
            
            if 'billing_login' not in existing_columns:
                columns_to_add.append("billing_login VARCHAR(128)")
            
            if 'billing_password_encrypted' not in existing_columns:
                columns_to_add.append("billing_password_encrypted TEXT")
            
            if 'payment_date' not in existing_columns:
                columns_to_add.append("payment_date DATE")
            
            if 'payment_reminder_sent' not in existing_columns:
                columns_to_add.append("payment_reminder_sent BOOLEAN DEFAULT FALSE")
            
            # Если нет полей для добавления, завершаем
            if not columns_to_add:
                logger.info("Все необходимые поля уже существуют в таблице server")
                return True
            
            # Создаем SQL-запрос для добавления полей
            statements = []
            for column_def in columns_to_add:
                statements.append(f"ALTER TABLE server ADD COLUMN {column_def};")
            
            sql = " ".join(statements)
            
            # Выполняем запрос
            db.session.execute(text(sql))
            db.session.commit()
            
            logger.info(f"Успешно добавлены поля: {', '.join(column.split()[0] for column in columns_to_add)}")
            return True
            
    except Exception as e:
        logger.error(f"Ошибка при добавлении полей в таблицу server: {str(e)}")
        db.session.rollback()
        return False

def set_initial_payment_dates():
    """
    Устанавливает начальные даты оплаты для всех серверов
    """
    try:
        with app.app_context():
            # Проверяем существующие колонки
            inspector = db.inspect(db.engine)
            existing_columns = [column['name'] for column in inspector.get_columns('server')]
            
            if 'payment_date' not in existing_columns:
                logger.error("Поле payment_date не существует в таблице server")
                return False
                
            # Получаем все серверы без даты оплаты
            from models import Server
            servers = Server.query.filter(Server.payment_date.is_(None)).all()
            
            if not servers:
                logger.info("Все серверы уже имеют установленную дату оплаты")
                return True
            
            # Устанавливаем дату оплаты на 30 дней вперёд от текущей даты
            next_month_date = datetime.now().date() + timedelta(days=30)
            
            for server in servers:
                server.payment_date = next_month_date
                logger.info(f"Установлена дата оплаты для сервера {server.name}: {next_month_date}")
            
            db.session.commit()
            logger.info(f"Установлены начальные даты оплаты для {len(servers)} серверов")
            return True
            
    except Exception as e:
        logger.error(f"Ошибка при установке начальных дат оплаты: {str(e)}")
        db.session.rollback()
        return False

if __name__ == "__main__":
    logger.info("Начало миграции полей биллинга...")
    
    # Добавляем поля в таблицу
    if add_billing_fields():
        # Если успешно добавили поля, устанавливаем начальные даты оплаты
        if set_initial_payment_dates():
            logger.info("Миграция полей биллинга завершена успешно")
        else:
            logger.error("Ошибка при установке начальных дат оплаты")
            sys.exit(1)
    else:
        logger.error("Ошибка при добавлении полей в таблицу server")
        sys.exit(1)