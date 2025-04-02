"""
Скрипт для добавления поля previous_ns_status в таблицу Domain
для отслеживания изменений статуса NS записей

Для запуска:
python add_previous_ns_status.py
"""

import logging
import sqlalchemy
from app import app, db

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_previous_ns_status_field():
    """
    Добавляет поле previous_ns_status в таблицу domain.
    """
    connection = None
    try:
        # Проверяем существование поля
        connection = db.engine.connect()
        inspector = sqlalchemy.inspect(db.engine)
        columns = [column['name'] for column in inspector.get_columns('domain')]
        
        if 'previous_ns_status' not in columns:
            # Добавляем поле
            connection.execute(sqlalchemy.text(
                'ALTER TABLE domain ADD COLUMN previous_ns_status VARCHAR(20) NULL;'
            ))
            logger.info("Поле previous_ns_status успешно добавлено в таблицу domain.")
            
            # Устанавливаем начальные значения
            connection.execute(sqlalchemy.text(
                'UPDATE domain SET previous_ns_status = ns_status;'
            ))
            logger.info("Начальные значения previous_ns_status установлены.")
        else:
            logger.info("Поле previous_ns_status уже существует в таблице domain.")
            
    except Exception as e:
        logger.error(f"Ошибка при добавлении поля previous_ns_status: {str(e)}")
        raise
    finally:
        if connection:
            connection.close()

def update_check_domains_ns_function():
    """
    Обновляет процедуру проверки NS доменов: добавляет обновление previous_ns_status
    после проверки статуса NS записей
    """
    try:
        logger.info("Обновление процедуры проверки NS доменов не требуется, код уже обновлен в файле tasks.py")
    except Exception as e:
        logger.error(f"Ошибка при обновлении процедуры проверки NS доменов: {str(e)}")
        raise

if __name__ == "__main__":
    logger.info("Начало добавления поля previous_ns_status в таблицу domain...")
    with app.app_context():
        add_previous_ns_status_field()
        update_check_domains_ns_function()
    logger.info("Добавление поля previous_ns_status в таблицу domain завершено.")