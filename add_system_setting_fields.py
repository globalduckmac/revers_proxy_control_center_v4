"""
Скрипт для добавления полей is_encrypted, created_at и updated_at в таблицу SystemSetting.

Для запуска:
python add_system_setting_fields.py
"""
import os
import sys
from sqlalchemy import inspect, Column, Boolean, DateTime
from datetime import datetime
from app import db, app


def add_system_setting_fields():
    """
    Добавляет поля is_encrypted, created_at и updated_at в таблицу system_setting.
    """
    with app.app_context():
        # Проверяем, существуют ли уже нужные колонки
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('system_setting')]
        
        # Добавляем недостающие колонки
        changes_made = False
        
        if 'is_encrypted' not in columns:
            print("Добавление колонки is_encrypted...")
            db.engine.execute('ALTER TABLE system_setting ADD COLUMN is_encrypted BOOLEAN DEFAULT FALSE')
            changes_made = True
        
        if 'created_at' not in columns:
            print("Добавление колонки created_at...")
            # Добавляем колонку со значением по умолчанию
            db.engine.execute(f"ALTER TABLE system_setting ADD COLUMN created_at TIMESTAMP DEFAULT '{datetime.utcnow()}'")
            changes_made = True
        
        if 'updated_at' not in columns:
            print("Добавление колонки updated_at...")
            # Добавляем колонку со значением по умолчанию
            db.engine.execute(f"ALTER TABLE system_setting ADD COLUMN updated_at TIMESTAMP DEFAULT '{datetime.utcnow()}'")
            changes_made = True
        
        if changes_made:
            print("Обновление таблицы system_setting успешно завершено!")
        else:
            print("Таблица system_setting уже содержит все необходимые поля.")


if __name__ == "__main__":
    add_system_setting_fields()