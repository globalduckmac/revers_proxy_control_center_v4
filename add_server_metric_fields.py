"""
Скрипт для добавления дополнительных полей в таблицу ServerMetric

Для запуска:
python add_server_metric_fields.py
"""
import logging
import sys
import time
from sqlalchemy import Column, BigInteger, Integer, Text
from sqlalchemy.exc import OperationalError

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_server_metric_fields():
    """
    Добавляет новые поля в таблицу server_metric для расширенных данных Glances API.
    """
    try:
        # Импортируем нужные модули
        from app import db
        from models import ServerMetric
        import sqlalchemy as sa
        
        logger.info("Начало процесса добавления новых полей в таблицу server_metric")
        
        # Проверяем существует ли поле cpu_cores
        inspector = sa.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('server_metric')]
        
        changes_made = False
        
        # Если колонки уже существуют, пропускаем их
        with db.engine.connect() as conn:
            if 'cpu_cores' not in columns:
                # Добавляем колонку cpu_cores
                logger.info("Добавление колонки cpu_cores")
                conn.execute(sa.text('ALTER TABLE server_metric ADD COLUMN cpu_cores INTEGER'))
                changes_made = True
                
            if 'memory_total' not in columns:
                # Добавляем колонку memory_total
                logger.info("Добавление колонки memory_total")
                conn.execute(sa.text('ALTER TABLE server_metric ADD COLUMN memory_total BIGINT'))
                changes_made = True
                
            if 'memory_used' not in columns:
                # Добавляем колонку memory_used
                logger.info("Добавление колонки memory_used")
                conn.execute(sa.text('ALTER TABLE server_metric ADD COLUMN memory_used BIGINT'))
                changes_made = True
                
            if 'disk_info' not in columns:
                # Добавляем колонку disk_info
                logger.info("Добавление колонки disk_info")
                conn.execute(sa.text('ALTER TABLE server_metric ADD COLUMN disk_info TEXT'))
                changes_made = True
                
            # Обновляем значение по умолчанию для collection_method
            logger.info("Обновление значения по умолчанию для collection_method")
            conn.execute(sa.text("ALTER TABLE server_metric ALTER COLUMN collection_method SET DEFAULT 'glances_api'"))
            conn.commit()
        
        if changes_made:
            logger.info("Поля успешно добавлены!")
        else:
            logger.info("Все требуемые поля уже существуют")
        
        logger.info("Миграция завершена успешно!")
        return True
        
    except OperationalError as e:
        logger.error(f"Ошибка базы данных: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при добавлении полей: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    # Создаем контекст приложения для работы с базой данных
    from app import app
    with app.app_context():
        result = add_server_metric_fields()
    sys.exit(0 if result else 1)