"""
Скрипт для добавления полей интеграции с FFPanel в таблицу Domain:
- ffpanel_enabled: флаг, указывающий, включена ли интеграция с FFPanel
- ffpanel_target_ip: отдельный IP-адрес для FFPanel (может отличаться от основного target_ip)

Для запуска:
python add_ffpanel_target_ip_field.py
"""

import logging
import sys
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from sqlalchemy import Column, Boolean, String
    from models import Domain, db
    import app
except ImportError as e:
    logger.error(f"Ошибка импорта: {e}")
    sys.exit(1)

def add_ffpanel_target_ip_fields():
    """
    Добавляет поля ffpanel_enabled и ffpanel_target_ip в таблицу Domain.
    """
    try:
        # Инициализация приложения, чтобы получить доступ к базе данных
        with app.app.app_context():
            # Проверяем, существуют ли уже столбцы
            inspector = db.inspect(db.engine)
            columns = [column['name'] for column in inspector.get_columns('domain')]
            
            # Добавляем новые столбцы, если они еще не существуют
            changes_made = False
            
            if 'ffpanel_enabled' not in columns:
                logger.info("Добавление столбца ffpanel_enabled в таблицу Domain")
                db.session.execute(
                    'ALTER TABLE domain ADD COLUMN ffpanel_enabled BOOLEAN DEFAULT FALSE'
                )
                changes_made = True
                
            if 'ffpanel_target_ip' not in columns:
                logger.info("Добавление столбца ffpanel_target_ip в таблицу Domain")
                db.session.execute(
                    'ALTER TABLE domain ADD COLUMN ffpanel_target_ip VARCHAR(45) DEFAULT NULL'
                )
                changes_made = True
                
            if changes_made:
                # Фиксируем изменения
                db.session.commit()
                logger.info("Новые столбцы успешно добавлены в таблицу Domain")
            else:
                logger.info("Все необходимые столбцы уже существуют в таблице Domain")
                
            # Обновляем ffpanel_enabled для доменов, у которых уже есть ffpanel_id
            update_count = db.session.execute(
                'UPDATE domain SET ffpanel_enabled = TRUE WHERE ffpanel_id IS NOT NULL AND ffpanel_id > 0'
            ).rowcount
            
            if update_count > 0:
                db.session.commit()
                logger.info(f"Флаг ffpanel_enabled установлен в TRUE для {update_count} доменов")
                
            return True
            
    except Exception as e:
        logger.error(f"Ошибка при добавлении столбцов: {e}")
        db.session.rollback()
        return False

if __name__ == "__main__":
    success = add_ffpanel_target_ip_fields()
    if success:
        logger.info("Миграция успешно завершена")
    else:
        logger.error("Миграция не удалась")
        sys.exit(1)