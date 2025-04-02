"""
Скрипт для синхронизации модели Domain с базой данных
Этот скрипт создает новую таблицу domain_new с текущей схемой модели Domain,
копирует данные из domain в domain_new, затем переименовывает таблицы
"""

import logging
from app import app, db
from models import Domain
from sqlalchemy import text

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sync_domain_model():
    """
    Синхронизирует модель Domain с базой данных путем создания новой таблицы
    """
    with app.app_context():
        try:
            # Сохраняем имя текущей таблицы
            old_table_name = Domain.__tablename__
            
            # Временно меняем имя таблицы, чтобы создать новую
            Domain.__tablename__ = 'domain_new'
            
            # Создаем новую таблицу
            db.create_all()
            logger.info("Создана новая таблица domain_new с обновленной схемой")
            
            # Копируем данные из старой таблицы в новую
            db.session.execute(text("""
                INSERT INTO domain_new (
                    id, name, target_ip, target_port, ssl_enabled, ssl_status,
                    is_active, created_at, updated_at, expected_nameservers,
                    ns_status, actual_nameservers, ns_check_date,
                    ffpanel_enabled, ffpanel_target_ip, ffpanel_id,
                    ffpanel_status, ffpanel_port, ffpanel_port_out,
                    ffpanel_port_ssl, ffpanel_port_out_ssl,
                    ffpanel_dns, ffpanel_last_sync
                )
                SELECT 
                    id, name, target_ip, target_port, ssl_enabled, ssl_status,
                    is_active, created_at, updated_at, expected_nameservers,
                    ns_status, actual_nameservers, ns_check_date,
                    ffpanel_enabled, ffpanel_target_ip, ffpanel_id,
                    ffpanel_status, ffpanel_port, ffpanel_port_out,
                    ffpanel_port_ssl, ffpanel_port_out_ssl,
                    ffpanel_dns, ffpanel_last_sync
                FROM domain
            """))
            logger.info("Данные скопированы из domain в domain_new")
            
            # Устанавливаем начальные значения для previous_ns_status
            db.session.execute(text("""
                UPDATE domain_new SET previous_ns_status = ns_status
            """))
            logger.info("Установлены начальные значения для поля previous_ns_status")
            
            # Переименовываем таблицы
            db.session.execute(text("ALTER TABLE domain RENAME TO domain_old"))
            db.session.execute(text("ALTER TABLE domain_new RENAME TO domain"))
            logger.info("Таблицы переименованы: domain -> domain_old, domain_new -> domain")
            
            # Восстанавливаем имя таблицы в модели
            Domain.__tablename__ = old_table_name
            
            # Создаем индексы на новой таблице, если они были в старой
            db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_domain_name ON domain (name)"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_domain_active ON domain (is_active)"))
            logger.info("Индексы созданы на новой таблице domain")
            
            # Сохраняем изменения
            db.session.commit()
            logger.info("Миграция схемы domain выполнена успешно")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при синхронизации модели Domain: {str(e)}")
            
            # Возвращаем имя таблицы в исходное состояние
            if Domain.__tablename__ != 'domain':
                Domain.__tablename__ = 'domain'
            
            raise e

if __name__ == "__main__":
    logger.info("Запуск синхронизации модели Domain...")
    sync_domain_model()
    logger.info("Синхронизация модели Domain завершена")