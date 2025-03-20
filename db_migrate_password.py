import os
import sys
import logging

from app import app, db
from models import Server
from sqlalchemy import text

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_server_passwords():
    """
    Миграция паролей серверов из обычного текста в хеширование
    
    1. Создает новую колонку ssh_password_hash
    2. Переносит существующие пароли в новую колонку с хешированием
    3. Удаляет старую колонку ssh_password
    """
    try:
        with app.app_context():
            # Шаг 1: Проверяем существование колонки ssh_password_hash
            logger.info("Checking if ssh_password_hash column exists...")
            with db.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='server' AND column_name='ssh_password_hash'"
                ))
                column_exists = result.scalar() is not None
            
            # Если колонка уже существует, пропустим первый шаг
            if not column_exists:
                logger.info("Adding new column ssh_password_hash...")
                with db.engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE server ADD COLUMN ssh_password_hash VARCHAR(256)"
                    ))
                    conn.commit()
            else:
                logger.info("Column ssh_password_hash already exists, skipping step 1.")
            
            # Шаг 2: Проверяем существование колонки ssh_password
            logger.info("Checking if ssh_password column exists...")
            with db.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='server' AND column_name='ssh_password'"
                ))
                old_column_exists = result.scalar() is not None
            
            if old_column_exists:
                # Получаем все серверы и их пароли в открытом виде
                logger.info("Migrating passwords from ssh_password to ssh_password_hash...")
                with db.engine.connect() as conn:
                    result = conn.execute(text(
                        "SELECT id, ssh_password FROM server WHERE ssh_password IS NOT NULL"
                    ))
                    servers_with_passwords = result.fetchall()
                
                # Хешируем пароли и сохраняем в новую колонку
                for server_id, password in servers_with_passwords:
                    if password:  # Проверка на null и пустую строку
                        server = Server.query.get(server_id)
                        if server:
                            logger.info(f"Hashing password for server ID {server_id}")
                            server.set_ssh_password(password)
                            db.session.add(server)
                
                db.session.commit()
                logger.info(f"Migrated {len(servers_with_passwords)} server passwords")
                
                # Шаг 3: Удаляем старую колонку
                logger.info("Removing old ssh_password column...")
                with db.engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE server DROP COLUMN ssh_password"
                    ))
                    conn.commit()
            else:
                logger.info("Column ssh_password does not exist, skipping steps 2 and 3.")
            
            logger.info("Migration completed successfully!")
            return True
    
    except Exception as e:
        logger.error(f"Error during migration: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Starting server password migration...")
    result = migrate_server_passwords()
    
    if result:
        logger.info("Migration completed successfully!")
        sys.exit(0)
    else:
        logger.error("Migration failed!")
        sys.exit(1)