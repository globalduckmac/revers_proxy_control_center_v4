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
            db.engine.execute("ALTER TABLE server ADD COLUMN ssh_encrypted_password TEXT;")
            print("Столбец ssh_encrypted_password успешно добавлен.")
        except Exception as e:
            print(f"Ошибка при добавлении столбца: {e}")
            sys.exit(1)

def encrypt_existing_passwords(skip_prompt=False):
    """
    Миграция паролей в зашифрованный формат.
    
    Args:
        skip_prompt: Если True, пропускает запрос подтверждения
    """
    if not skip_prompt:
        confirm = input("ВНИМАНИЕ: Для миграции паролей требуется временно ввести пароли в открытом виде.\n"
                        "После выполнения миграции пароли будут доступны только для авторизации.\n"
                        "Продолжить? (y/n): ")
        
        if confirm.lower() != 'y':
            print("Миграция отменена.")
            return
    
    with app.app_context():
        servers = Server.query.all()
        servers_with_password = [s for s in servers if s.ssh_password_hash and not s.ssh_key]
        
        if not servers_with_password:
            print("Нет серверов с паролями для миграции.")
            return
        
        print(f"Найдено {len(servers_with_password)} серверов с паролями для миграции.")
        
        migrated_count = 0
        for server in servers_with_password:
            print(f"Обработка сервера: {server.name} ({server.ip_address})")
            
            password = input(f"Введите SSH пароль для сервера {server.name} ({server.ip_address}): ")
            
            # Проверяем введенный пароль
            if server.check_ssh_password(password):
                # Шифруем пароль и сохраняем
                server.ssh_encrypted_password = encrypt_password(password)
                migrated_count += 1
                print(f"Пароль для сервера {server.name} успешно зашифрован.")
            else:
                print(f"Неверный пароль для сервера {server.name}. Сервер будет пропущен.")
        
        # Сохраняем изменения
        db.session.commit()
        
        print(f"Миграция завершена. Обработано серверов: {migrated_count} из {len(servers_with_password)}.")
        print("Примечание: Теперь автоматическая проверка серверов будет работать с зашифрованными паролями.")

if __name__ == "__main__":
    add_encrypted_password_column()
    encrypt_existing_passwords()