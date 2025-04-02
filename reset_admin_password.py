"""
Скрипт для сброса пароля администратора

Для запуска:
python reset_admin_password.py
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from app import app, db
from models import User
from werkzeug.security import generate_password_hash

def reset_admin_password():
    """
    Сбрасывает пароль администратора на заданное значение
    """
    with app.app_context():
        # Находим пользователя admin
        admin_user = User.query.filter_by(username='admin').first()
        
        if not admin_user:
            print("Ошибка: Пользователь admin не найден!")
            return False
        
        # Устанавливаем новый пароль
        new_password = "admin123"  # Стандартный пароль
        admin_user.password_hash = generate_password_hash(new_password)
        
        # Сохраняем изменения
        db.session.commit()
        
        print(f"Пароль администратора сброшен на: {new_password}")
        return True

if __name__ == "__main__":
    reset_admin_password()