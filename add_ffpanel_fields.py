"""
Скрипт для добавления полей интеграции с FFPanel в таблицу Domain

Для запуска:
python add_ffpanel_fields.py
"""

import os
import sys
from datetime import datetime

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, text
from sqlalchemy.sql import select

def add_ffpanel_fields():
    """
    Добавляет поля для интеграции с FFPanel в таблицу Domain.
    """
    # Подключение к базе данных
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("Ошибка: переменная окружения DATABASE_URL не найдена.")
        sys.exit(1)
    
    engine = create_engine(db_url)
    meta = MetaData()
    meta.reflect(bind=engine)
    
    # Проверяем наличие таблицы Domain
    if 'domain' not in meta.tables:
        print("Ошибка: таблица 'domain' не найдена в базе данных.")
        sys.exit(1)
    
    domain_table = meta.tables['domain']
    columns_to_add = [
        ('ffpanel_id', Column('ffpanel_id', Integer, nullable=True)),
        ('ffpanel_status', Column('ffpanel_status', String(20), default='not_synced')),
        ('ffpanel_port', Column('ffpanel_port', String(10), default='80')),
        ('ffpanel_port_out', Column('ffpanel_port_out', String(10), default='80')),
        ('ffpanel_port_ssl', Column('ffpanel_port_ssl', String(10), default='443')),
        ('ffpanel_port_out_ssl', Column('ffpanel_port_out_ssl', String(10), default='443')),
        ('ffpanel_dns', Column('ffpanel_dns', String(255), nullable=True)),
        ('ffpanel_last_sync', Column('ffpanel_last_sync', DateTime, nullable=True))
    ]
    
    # Проверяем существующие колонки
    existing_columns = set(domain_table.columns.keys())
    
    with engine.begin() as conn:
        for column_name, column_def in columns_to_add:
            if column_name not in existing_columns:
                print(f"Добавление колонки {column_name}...")
                # Для datetime нужно использовать TIMESTAMP в PostgreSQL
                sql_type = "TIMESTAMP"
                if isinstance(column_def.type, DateTime):
                    sql_type = "TIMESTAMP"
                elif isinstance(column_def.type, String):
                    sql_type = f"VARCHAR({column_def.type.length})"
                elif isinstance(column_def.type, Integer):
                    sql_type = "INTEGER"
                
                conn.execute(text(f"ALTER TABLE domain ADD COLUMN {column_name} {sql_type}"))
                print(f"Колонка {column_name} успешно добавлена.")
            else:
                print(f"Колонка {column_name} уже существует.")
    
    print("Миграция успешно завершена.")

if __name__ == "__main__":
    add_ffpanel_fields()