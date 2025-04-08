-- Проверка и добавление колонки collection_method в таблицу external_server_metric
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'external_server_metric' 
        AND column_name = 'collection_method'
    ) THEN
        -- Добавляем колонку collection_method
        EXECUTE 'ALTER TABLE external_server_metric ADD COLUMN collection_method VARCHAR(20) DEFAULT ''glances_api''';
        RAISE NOTICE 'Колонка collection_method добавлена в таблицу external_server_metric.';
    ELSE
        RAISE NOTICE 'Колонка collection_method уже существует в таблице external_server_metric.';
    END IF;
END $$;