#!/usr/bin/env python3
"""
Скрипт для проверки и активации интеграции с FFPanel для определенного домена.
Позволяет включить FFPanel для домена и синхронизировать его, даже если это не выполняется через веб-интерфейс.

Запуск:
python domain_ffpanel_check.py <domain_id>
"""

import sys
import logging
from datetime import datetime

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_domain_ffpanel_status(domain_id):
    """Проверяет текущий статус FFPanel интеграции для домена."""
    try:
        from app import app
        from models import Domain
        
        with app.app_context():
            domain = Domain.query.get(domain_id)
            if not domain:
                logger.error(f"Домен с ID {domain_id} не найден")
                return False
            
            logger.info(f"Домен: {domain.name} (ID: {domain_id})")
            logger.info(f"FFPanel интеграция включена: {domain.ffpanel_enabled}")
            logger.info(f"FFPanel ID: {domain.ffpanel_id or 'Не установлен'}")
            logger.info(f"FFPanel статус: {domain.ffpanel_status or 'Не установлен'}")
            logger.info(f"FFPanel целевой IP: {domain.ffpanel_target_ip or domain.target_ip or 'Не установлен'}")
            
            if domain.ffpanel_last_sync:
                logger.info(f"Последняя синхронизация: {domain.ffpanel_last_sync}")
            else:
                logger.info("Последняя синхронизация: Никогда")
            
            return domain
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса FFPanel для домена: {str(e)}")
        return False

def enable_ffpanel_for_domain(domain_id):
    """Включает FFPanel интеграцию для домена."""
    try:
        from app import app, db
        from models import Domain
        
        with app.app_context():
            domain = Domain.query.get(domain_id)
            if not domain:
                logger.error(f"Домен с ID {domain_id} не найден")
                return False
            
            domain.ffpanel_enabled = True
            if not domain.ffpanel_target_ip:
                domain.ffpanel_target_ip = domain.target_ip
            
            # Устанавливаем стандартные порты, если они не заданы
            if not domain.ffpanel_port:
                domain.ffpanel_port = '80'
            if not domain.ffpanel_port_out:
                domain.ffpanel_port_out = '80'
            if not domain.ffpanel_port_ssl:
                domain.ffpanel_port_ssl = '443'
            if not domain.ffpanel_port_out_ssl:
                domain.ffpanel_port_out_ssl = '443'
            
            db.session.commit()
            logger.info(f"FFPanel интеграция включена для домена {domain.name}")
            return True
    except Exception as e:
        logger.error(f"Ошибка при включении FFPanel для домена: {str(e)}")
        return False

def sync_domain_with_ffpanel(domain_id):
    """Синхронизирует домен с FFPanel."""
    try:
        from app import app
        from modules.domain_manager import DomainManager
        
        with app.app_context():
            logger.info(f"Запуск синхронизации домена {domain_id} с FFPanel...")
            result = DomainManager.sync_domain_with_ffpanel(domain_id)
            
            if result['success']:
                logger.info(f"Синхронизация успешна: {result['message']}")
            else:
                logger.error(f"Ошибка синхронизации: {result['message']}")
            
            return result
    except Exception as e:
        logger.error(f"Исключение при синхронизации домена с FFPanel: {str(e)}")
        return {'success': False, 'message': str(e)}

def main():
    """Основная функция скрипта."""
    if len(sys.argv) < 2:
        print("Использование: python domain_ffpanel_check.py <domain_id>")
        return 1
    
    try:
        domain_id = int(sys.argv[1])
    except ValueError:
        print(f"Ошибка: {sys.argv[1]} не является корректным ID домена (должно быть число)")
        return 1
    
    logger.info(f"=== Проверка FFPanel интеграции для домена ID {domain_id} ===")
    
    # Проверяем текущий статус домена
    domain = check_domain_ffpanel_status(domain_id)
    if not domain:
        return 1
    
    # Если FFPanel не включен, предлагаем включить
    if not domain.ffpanel_enabled:
        answer = input("FFPanel не включен для этого домена. Хотите включить? (y/n): ")
        if answer.lower() == 'y':
            if enable_ffpanel_for_domain(domain_id):
                logger.info("FFPanel успешно включен")
            else:
                logger.error("Не удалось включить FFPanel")
                return 1
        else:
            logger.info("FFPanel остался выключенным")
            return 0
    
    # Если FFPanel включен, но нет ID, предлагаем синхронизировать
    if domain.ffpanel_enabled and not domain.ffpanel_id:
        answer = input("Домен не синхронизирован с FFPanel. Хотите синхронизировать? (y/n): ")
        if answer.lower() == 'y':
            result = sync_domain_with_ffpanel(domain_id)
            return 0 if result['success'] else 1
        else:
            logger.info("Синхронизация отменена")
            return 0
    
    # Если домен уже синхронизирован, предлагаем обновить
    if domain.ffpanel_id:
        answer = input("Домен уже синхронизирован с FFPanel. Хотите обновить? (y/n): ")
        if answer.lower() == 'y':
            result = sync_domain_with_ffpanel(domain_id)
            return 0 if result['success'] else 1
        else:
            logger.info("Обновление отменено")
            return 0
    
    return 0

if __name__ == "__main__":
    sys.exit(main())