-- Проверка и добавление колонки metric_value в таблицу external_server_metric
DO $$
BEGIN
    -- Проверяем существование колонки metric_value
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'metric_value'
    ) THEN
        -- Добавляем колонку metric_value
        EXECUTE 'ALTER TABLE external_server_metric ADD COLUMN metric_value TEXT NULL';
        RAISE NOTICE 'Колонка metric_value добавлена в таблицу external_server_metric.';
    ELSE
        -- Проверяем, является ли колонка NOT NULL
        IF EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = 'external_server_metric' 
            AND column_name = 'metric_value' 
            AND is_nullable = 'NO'
        ) THEN
            -- Изменяем колонку, делая её NULL
            EXECUTE 'ALTER TABLE external_server_metric ALTER COLUMN metric_value DROP NOT NULL';
            RAISE NOTICE 'Колонка metric_value изменена на NULL в таблице external_server_metric.';
        ELSE
            RAISE NOTICE 'Колонка metric_value уже существует и может быть NULL в таблице external_server_metric.';
        END IF;
    END IF;

    -- Проверяем и добавляем другие колонки, если это необходимо
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'timestamp'
    ) THEN
        EXECUTE 'ALTER TABLE external_server_metric ADD COLUMN timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL';
        RAISE NOTICE 'Колонка timestamp добавлена в таблицу external_server_metric.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'cpu_usage'
    ) THEN
        EXECUTE 'ALTER TABLE external_server_metric ADD COLUMN cpu_usage DOUBLE PRECISION';
        RAISE NOTICE 'Колонка cpu_usage добавлена в таблицу external_server_metric.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'memory_usage'
    ) THEN
        EXECUTE 'ALTER TABLE external_server_metric ADD COLUMN memory_usage DOUBLE PRECISION';
        RAISE NOTICE 'Колонка memory_usage добавлена в таблицу external_server_metric.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'disk_usage'
    ) THEN
        EXECUTE 'ALTER TABLE external_server_metric ADD COLUMN disk_usage DOUBLE PRECISION';
        RAISE NOTICE 'Колонка disk_usage добавлена в таблицу external_server_metric.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'load_average'
    ) THEN
        EXECUTE 'ALTER TABLE external_server_metric ADD COLUMN load_average VARCHAR(30)';
        RAISE NOTICE 'Колонка load_average добавлена в таблицу external_server_metric.';
    END IF;

    -- Убедимся, что колонка metric_type имеет значение по умолчанию
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'metric_type'
    ) THEN
        EXECUTE 'ALTER TABLE external_server_metric ALTER COLUMN metric_type SET DEFAULT ''system''';
        RAISE NOTICE 'Для колонки metric_type установлено значение по умолчанию ''system''.';
    END IF;

    -- Убедимся, что колонка metric_name имеет значение по умолчанию
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'metric_name'
    ) THEN
        EXECUTE 'ALTER TABLE external_server_metric ALTER COLUMN metric_name SET DEFAULT ''general''';
        RAISE NOTICE 'Для колонки metric_name установлено значение по умолчанию ''general''.';
    END IF;
END $$;