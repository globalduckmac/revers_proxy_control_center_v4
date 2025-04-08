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
CREATE TABLE IF NOT EXISTS external_server_metric (
    id SERIAL PRIMARY KEY,
    external_server_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cpu_usage FLOAT,
    memory_usage FLOAT,
    disk_usage FLOAT,
    load_average TEXT,
    collection_method VARCHAR(255),
    FOREIGN KEY (external_server_id) REFERENCES external_server(id) ON DELETE CASCADE
);

-- Проверяем и добавляем колонку timestamp, если она отсутствует
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'timestamp'
    ) THEN
        ALTER TABLE external_server_metric ADD COLUMN timestamp TIMESTAMP;
    END IF;
END $$;
