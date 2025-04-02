import os
import sys
from datetime import datetime
from sqlalchemy import text

from app import app, db
from models import Server, Domain, ExternalServer

def add_active_fields():
    with app.app_context():
        # Создаем соединение с базой данных
        connection = db.engine.connect()
        
        try:
            print("Начинаем добавление полей is_active и last_status в таблицы...")
            
            # Добавляем столбец is_active в таблицу server
            try:
                connection.execute(text("ALTER TABLE server ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
                print("Поле is_active добавлено в таблицу Server")
            except Exception as e:
                if "already exists" in str(e):
                    print("Поле is_active уже существует в таблице Server")
                else:
                    print(f"Ошибка при добавлении поля is_active в таблицу Server: {e}")
            
            # Добавляем столбец last_status в таблицу server
            try:
                connection.execute(text("ALTER TABLE server ADD COLUMN last_status VARCHAR(20) DEFAULT 'pending'"))
                print("Поле last_status добавлено в таблицу Server")
            except Exception as e:
                if "already exists" in str(e):
                    print("Поле last_status уже существует в таблице Server")
                else:
                    print(f"Ошибка при добавлении поля last_status в таблицу Server: {e}")
            
            # Добавляем столбец is_active в таблицу domain
            try:
                connection.execute(text("ALTER TABLE domain ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
                print("Поле is_active добавлено в таблицу Domain")
            except Exception as e:
                if "already exists" in str(e):
                    print("Поле is_active уже существует в таблице Domain")
                else:
                    print(f"Ошибка при добавлении поля is_active в таблицу Domain: {e}")
            
            # Фиксируем транзакцию
            connection.commit()
            print("Миграция успешно завершена")
            
        except Exception as e:
            print(f"Ошибка при выполнении миграции: {e}")
            connection.rollback()
        finally:
            connection.close()

if __name__ == "__main__":
    add_active_fields()