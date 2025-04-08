-- Исправленный скрипт для создания/обновления таблиц внешних серверов
-- Версия 5 с добавлением поля metric_value и других необходимых полей

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

    -- Теперь проверяем и добавляем metric_value, если оно отсутствует
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'metric_value'
    ) THEN
        -- Если поле отсутствует, добавляем его с возможностью NULL
        ALTER TABLE external_server_metric ADD COLUMN metric_value TEXT;
    END IF;
    
    -- Решаем проблему с NOT NULL constraint на metric_value, если оно существует
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'metric_value'
        AND is_nullable = 'NO'  -- Проверяем, что поле NOT NULL
    ) THEN
        -- Альтернатива 1: Делаем поле nullable
        ALTER TABLE external_server_metric ALTER COLUMN metric_value DROP NOT NULL;
        
        -- Альтернатива 2: Если нужно оставить NOT NULL, но с дефолтным значением
        -- ALTER TABLE external_server_metric ALTER COLUMN metric_value SET DEFAULT '0';
        -- UPDATE external_server_metric SET metric_value = '0' WHERE metric_value IS NULL;
    END IF;
END $$;
