"""
Скрипт для изменения пароля администратора

Для запуска:
python change_admin_password.py
"""

import sys
import logging
from app import app, db
from models import User

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def change_admin_password(new_password=None):
    """
    Изменяет пароль администратора.
    
    Args:
        new_password: Новый пароль для администратора. Если None, запрашивает с консоли.
    
    Returns:
        bool: True если пароль успешно изменен, False в случае ошибки
    """
    # Инициализируем Flask контекст
    with app.app_context():
        try:
            # Находим пользователя с правами администратора
            admin_user = User.query.filter_by(is_admin=True).first()
            
            if not admin_user:
                logger.error("Администратор не найден в базе данных")
                return False
            
            # Если пароль не передан, запрашиваем его из консоли
            if not new_password:
                import getpass
                print(f"Изменение пароля для администратора: {admin_user.username}")
                new_password = getpass.getpass("Введите новый пароль: ")
                confirm_password = getpass.getpass("Подтвердите новый пароль: ")
                
                if new_password != confirm_password:
                    logger.error("Пароли не совпадают")
                    return False
                
                if not new_password:
                    logger.error("Пароль не может быть пустым")
                    return False
            
            # Устанавливаем новый пароль
            admin_user.set_password(new_password)
            db.session.commit()
            
            logger.info(f"Пароль для администратора {admin_user.username} успешно изменен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при изменении пароля администратора: {str(e)}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    # Если скрипт запущен напрямую, то запрашиваем пароль и изменяем
    import argparse
    
    parser = argparse.ArgumentParser(description='Изменение пароля администратора')
    parser.add_argument('--password', help='Новый пароль (если не указан, будет запрошен)')
    
    args = parser.parse_args()
    
    if change_admin_password(args.password):
        sys.exit(0)
    else:
        sys.exit(1)