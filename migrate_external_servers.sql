
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
