"""
Скрипт для добавления поля ssh_encrypted_password в таблицу Server
и перенос существующих паролей в зашифрованный формат

Для запуска:
python add_encrypted_password.py
"""

import os
import sys
from app import app, db
from models import Server, decrypt_password, encrypt_password

def add_encrypted_password_column():
    """
    Добавляет столбец ssh_encrypted_password в таблицу Server.
    """
    print("Добавление столбца ssh_encrypted_password в таблицу Server...")
    
    with app.app_context():
        # Проверяем, существует ли уже столбец
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        columns = [column['name'] for column in inspector.get_columns('server')]
        
        if 'ssh_encrypted_password' in columns:
            print("Столбец ssh_encrypted_password уже существует.")
            return
        
        # Добавляем столбец
        try:
            # В новых версиях SQLAlchemy используем другой метод
            with db.engine.connect() as conn:
                conn.execute(db.text("ALTER TABLE server ADD COLUMN ssh_encrypted_password TEXT;"))
                conn.commit()
            print("Столбец ssh_encrypted_password успешно добавлен.")
        except Exception as e:
            print(f"Ошибка при добавлении столбца: {e}")
            sys.exit(1)

def encrypt_existing_passwords(test_password="test123"):
    """
    Миграция паролей в зашифрованный формат с использованием тестового пароля.
    В реальной системе пароли должны быть введены пользователем.
    
    Args:
        test_password: Тестовый пароль для шифрования (только для тестов)
    """
    print("Начинаем миграцию паролей в зашифрованный формат (для тестирования)")
    
    with app.app_context():
        servers = Server.query.all()
        servers_with_password = [s for s in servers if s.ssh_password_hash and not s.ssh_key]
        
        if not servers_with_password:
            print("Нет серверов с паролями для миграции.")
            return
        
        print(f"Найдено {len(servers_with_password)} серверов с паролями для миграции.")
        
        # В тестовой среде просто шифруем тестовый пароль для каждого сервера
        # В продакшене нужно запрашивать настоящие пароли у пользователя
        migrated_count = 0
        for server in servers_with_password:
            print(f"Обработка сервера: {server.name} ({server.ip_address})")
            
            # Шифруем пароль для автоматических проверок
            server.ssh_encrypted_password = encrypt_password(test_password)
            migrated_count += 1
            print(f"Пароль для сервера {server.name} успешно зашифрован.")
        
        # Сохраняем изменения
        db.session.commit()
        
        print(f"Миграция завершена. Обработано серверов: {migrated_count} из {len(servers_with_password)}.")
        print("Примечание: В тестовой среде для всех серверов используется один тестовый пароль.")
        print("В продакшене необходимо запросить у пользователя актуальные пароли и зашифровать их.")

if __name__ == "__main__":
    add_encrypted_password_column()
    encrypt_existing_passwords()