#!/usr/bin/env python
"""
Скрипт для добавления поля extra_data в таблицу ProxyConfig

Для запуска:
python add_proxy_extra_data.py
"""

from app import app, db
import sys

def add_extra_data_field():
    """
    Добавляет поле extra_data в таблицу proxy_config для хранения 
    дополнительных данных конфигурации в формате JSON
    """
    with app.app_context():
        try:
            # Импортируем text для SQL выражений
            from sqlalchemy import text
            
            # Проверяем существование колонки
            check_column_query = text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='proxy_config' AND column_name='extra_data';
            """)
            
            result = db.session.execute(check_column_query).fetchone()
            
            if result:
                print("Колонка extra_data уже существует в таблице proxy_config.")
                return
                
            # Добавляем колонку
            alter_table_query = text("""
            ALTER TABLE proxy_config ADD COLUMN extra_data TEXT NULL;
            """)
            
            db.session.execute(alter_table_query)
            db.session.commit()
            
            print("Колонка extra_data успешно добавлена в таблицу proxy_config.")
            
        except Exception as e:
            db.session.rollback()
            print(f"Ошибка при добавлении колонки extra_data: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    print("Запуск миграции для добавления поля extra_data в таблицу proxy_config...")
    add_extra_data_field()
    print("Миграция завершена.")