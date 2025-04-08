-- Исправленный скрипт для создания/обновления таблиц внешних серверов

-- Добавляем колонку glances_enabled в таблицу external_server
ALTER TABLE external_server ADD COLUMN IF NOT EXISTS glances_enabled BOOLEAN DEFAULT TRUE;

-- Проверяем, существует ли поле last_status, и переименовываем в status, если нужно
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server' 
        AND column_name = 'last_status'
        AND column_name NOT IN (
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'external_server'
            AND column_name = 'status'
        )
    ) THEN
        ALTER TABLE external_server RENAME COLUMN last_status TO status;
    END IF;
END $$;

-- Проверяем существование таблицы external_server_metric
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_name = 'external_server_metric'
    ) THEN
        -- Создаем новую таблицу с правильными полями
        CREATE TABLE external_server_metric (
            id SERIAL PRIMARY KEY,
            external_server_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            timestamp TIMESTAMP,
            cpu_usage FLOAT,
            memory_usage FLOAT,
            disk_usage FLOAT,
            load_average TEXT,
            collection_method VARCHAR(255),
            FOREIGN KEY (external_server_id) REFERENCES external_server(id) ON DELETE CASCADE
        );
    ELSE
        -- Таблица уже существует, проверяем и добавляем отсутствующие поля
        -- Добавляем колонку timestamp, если она отсутствует
        IF NOT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'external_server_metric' 
            AND column_name = 'timestamp'
        ) THEN
            ALTER TABLE external_server_metric ADD COLUMN timestamp TIMESTAMP;
        END IF;
        
        -- Добавляем колонку cpu_usage, если она отсутствует
        IF NOT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'external_server_metric' 
            AND column_name = 'cpu_usage'
        ) THEN
            ALTER TABLE external_server_metric ADD COLUMN cpu_usage FLOAT;
        END IF;
        
        -- Добавляем колонку memory_usage, если она отсутствует
        IF NOT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'external_server_metric' 
            AND column_name = 'memory_usage'
        ) THEN
            ALTER TABLE external_server_metric ADD COLUMN memory_usage FLOAT;
        END IF;
        
        -- Добавляем колонку disk_usage, если она отсутствует
        IF NOT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'external_server_metric' 
            AND column_name = 'disk_usage'
        ) THEN
            ALTER TABLE external_server_metric ADD COLUMN disk_usage FLOAT;
        END IF;
        
        -- Добавляем колонку load_average, если она отсутствует
        IF NOT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'external_server_metric' 
            AND column_name = 'load_average'
        ) THEN
            ALTER TABLE external_server_metric ADD COLUMN load_average TEXT;
        END IF;
        
        -- Добавляем колонку collection_method, если она отсутствует
        IF NOT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'external_server_metric' 
            AND column_name = 'collection_method'
        ) THEN
            ALTER TABLE external_server_metric ADD COLUMN collection_method VARCHAR(255);
        END IF;
    END IF;
END $$;
