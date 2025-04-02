"""
Скрипт для добавления полей метрик Glances в таблицу Server

Для запуска:
python add_glances_metrics_fields.py
"""

import logging
from app import app, db
from sqlalchemy import text

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_glances_metrics_fields():
    """
    Добавляет поля для хранения метрик Glances в таблицу server.
    """
    with app.app_context():
        try:
            # Проверяем существование колонок для метрик
            metrics_columns = [
                'glances_cpu', 'glances_memory', 'glances_disk', 
                'glances_network', 'glances_load', 'glances_uptime'
            ]
            
            # Получаем список существующих колонок
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'server'
            """))
            existing_columns = {row[0] for row in result}
            
            # Добавляем отсутствующие колонки
            columns_to_add = {}
            
            if 'glances_cpu' not in existing_columns:
                columns_to_add['glances_cpu'] = 'FLOAT'
            
            if 'glances_memory' not in existing_columns:
                columns_to_add['glances_memory'] = 'FLOAT'
            
            if 'glances_disk' not in existing_columns:
                columns_to_add['glances_disk'] = 'TEXT'
            
            if 'glances_network' not in existing_columns:
                columns_to_add['glances_network'] = 'TEXT'
            
            if 'glances_load' not in existing_columns:
                columns_to_add['glances_load'] = 'TEXT'
            
            if 'glances_uptime' not in existing_columns:
                columns_to_add['glances_uptime'] = 'BIGINT'
            
            # Если нет колонок для добавления, выходим
            if not columns_to_add:
                logger.info("Все необходимые колонки для метрик Glances уже существуют")
                return
            
            # Добавляем каждую колонку отдельным запросом
            for column_name, column_type in columns_to_add.items():
                db.session.execute(text(f"""
                    ALTER TABLE server ADD COLUMN {column_name} {column_type}
                """))
                logger.info(f"Добавлена колонка {column_name} типа {column_type} в таблицу server")
            
            # Сохраняем изменения
            db.session.commit()
            logger.info("Все необходимые колонки для метрик Glances успешно добавлены")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при добавлении колонок метрик Glances: {str(e)}")
            raise

if __name__ == "__main__":
    logger.info("Запуск добавления полей метрик Glances...")
    add_glances_metrics_fields()
    logger.info("Добавление полей метрик Glances завершено")