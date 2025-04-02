"""
Скрипт для обновления схемы базы данных
Этот скрипт перезапускает весь контекст SQLAlchemy и пересоздаёт недостающие колонки
"""

import logging
from app import app, db
from models import Domain

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_schema():
    """
    Обновляет схему базы данных, чтобы она соответствовала моделям ORM
    """
    try:
        with app.app_context():
            # Создаем недостающие колонки
            db.create_all()
            
            # Проверяем, была ли добавлена колонка previous_ns_status
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            columns = [column['name'] for column in inspector.get_columns('domain')]
            
            if 'previous_ns_status' in columns:
                logger.info("Колонка previous_ns_status существует в базе данных")
                
                # Проверяем, заполнены ли начальные значения
                result = db.session.execute(db.text("SELECT COUNT(*) FROM domain WHERE previous_ns_status IS NULL"))
                null_count = result.scalar()
                
                if null_count > 0:
                    # Заполняем начальные значения
                    db.session.execute(db.text("UPDATE domain SET previous_ns_status = ns_status WHERE previous_ns_status IS NULL"))
                    db.session.commit()
                    logger.info(f"Заполнены начальные значения для {null_count} записей в колонке previous_ns_status")
            else:
                logger.error("Колонка previous_ns_status отсутствует в базе данных после попытки её создания")
                
    except Exception as e:
        logger.error(f"Ошибка при обновлении схемы базы данных: {str(e)}")
        raise

if __name__ == "__main__":
    logger.info("Запуск обновления схемы базы данных...")
    update_schema()
    logger.info("Обновление схемы базы данных завершено")