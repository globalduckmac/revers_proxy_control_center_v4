#!/usr/bin/env python
"""
Скрипт для миграции данных из старой таблицы external_server в новую external_servers

Для запуска:
python migrate_external_servers.py
"""

import os
import sys
import datetime
from app import create_app, db
from models import ExternalServer

def migrate_external_servers():
    """
    Переносит данные из старой таблицы external_server в новую таблицу external_servers.
    """
    print("Начинаем миграцию данных из старой таблицы external_server в новую external_servers...")
    
    try:
        # Создаем временную модель для старой таблицы
        class OldExternalServer(db.Model):
            __tablename__ = 'external_server'
            __table_args__ = {'extend_existing': True}
            
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(64))
            ip_address = db.Column(db.String(45))
            description = db.Column(db.Text)
            is_active = db.Column(db.Boolean)
            created_at = db.Column(db.DateTime)
            updated_at = db.Column(db.DateTime)
            last_check = db.Column(db.DateTime)
            last_status = db.Column(db.String(32))
            glances_port = db.Column(db.Integer)
        
        # Получаем все старые серверы
        old_servers = OldExternalServer.query.all()
        
        if not old_servers:
            print("Старая таблица external_server пуста или не существует.")
            return
        
        print(f"Найдено {len(old_servers)} записей в старой таблице.")
        
        # Проверяем, нет ли уже в новой таблице серверов с такими же IP-адресами
        migrated_count = 0
        skipped_count = 0
        
        for old_server in old_servers:
            # Проверяем, существует ли уже такой сервер в новой таблице
            existing = ExternalServer.query.filter_by(ip_address=old_server.ip_address).first()
            
            if existing:
                print(f"Сервер с IP {old_server.ip_address} уже существует в новой таблице. Пропускаем.")
                skipped_count += 1
                continue
            
            # Создаем новый сервер в новой таблице
            new_server = ExternalServer(
                name=old_server.name,
                ip_address=old_server.ip_address,
                description=old_server.description,
                is_active=old_server.is_active,
                created_at=old_server.created_at or datetime.datetime.utcnow(),
                updated_at=old_server.updated_at or datetime.datetime.utcnow(),
                last_check_time=old_server.last_check,
                last_status=old_server.last_status or 'unknown',
                glances_port=old_server.glances_port or 61208
            )
            
            db.session.add(new_server)
            migrated_count += 1
        
        # Сохраняем изменения
        db.session.commit()
        
        print(f"Миграция завершена. Мигрировано: {migrated_count}, пропущено: {skipped_count}")
        
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при миграции данных: {str(e)}")
        return False
    
    return True

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        migrate_external_servers()