-- Исправленный скрипт для создания/обновления таблиц внешних серверов
-- Версия 4 с добавлением поля metric_name и других необходимых полей

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

-- Обновляем таблицу external_server_metric
DO $$
BEGIN
    -- Сначала решаем проблему с metric_type
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'metric_type'
        AND is_nullable = 'NO'  -- Проверяем, что поле NOT NULL
    ) THEN
        -- Если у нас таблица с NOT NULL полем metric_type, сначала пробуем установить значение по умолчанию
        ALTER TABLE external_server_metric ALTER COLUMN metric_type SET DEFAULT 'system';
        
        -- Обновляем существующие NULL значения
        UPDATE external_server_metric SET metric_type = 'system' WHERE metric_type IS NULL;
    END IF;
    
    -- Затем решаем проблему с metric_name
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'metric_name'
        AND is_nullable = 'NO'  -- Проверяем, что поле NOT NULL
    ) THEN
        -- Если у нас таблица с NOT NULL полем metric_name, сначала пробуем установить значение по умолчанию
        ALTER TABLE external_server_metric ALTER COLUMN metric_name SET DEFAULT 'general';
        
        -- Обновляем существующие NULL значения
        UPDATE external_server_metric SET metric_name = 'general' WHERE metric_name IS NULL;
    END IF;

    -- Модифицируем SQL команду в коде приложения, чтобы включить эти поля
    
    -- Добавляем другие недостающие поля
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
END $$;
