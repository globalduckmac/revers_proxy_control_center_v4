#!/usr/bin/env python
"""
Скрипт для создания SQL файла миграции данных из старой таблицы external_server в новую external_servers

Для запуска:
python create_migration_script.py
"""

def create_migration_script():
    """
    Создает SQL файл для миграции данных из старой таблицы в новую
    """
    sql = """
-- Миграция данных из старой таблицы external_server в новую external_servers
INSERT INTO external_servers 
(name, ip_address, description, is_active, created_at, updated_at, last_check_time, last_status, glances_port)
SELECT 
    name, 
    ip_address, 
    description, 
    is_active, 
    created_at, 
    updated_at, 
    last_check, 
    last_status, 
    glances_port
FROM external_server
WHERE ip_address NOT IN (SELECT ip_address FROM external_servers);

-- Опционально: Удаление старой таблицы (раскомментируйте, если нужно)
-- DROP TABLE external_server;
"""
    
    with open('migrate_external_servers.sql', 'w') as f:
        f.write(sql)
    
    print("SQL скрипт миграции создан: migrate_external_servers.sql")
    print("Чтобы выполнить миграцию, запустите:")
    print("psql [ваш_url_бд] -f migrate_external_servers.sql")

if __name__ == '__main__':
    create_migration_script()