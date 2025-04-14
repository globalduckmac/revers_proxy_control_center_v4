#!/usr/bin/env python3
"""
Скрипт для диагностики и отладки интеграции с FFPanel API.
Проверяет подключение к FFPanel, настройки токена и возможность получения данных.

python3 debug_ffpanel_integration.py
"""

import os
import sys
import json
import logging
from datetime import datetime

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_token_from_environment():
    """Получает токен FFPanel из переменной окружения."""
    token = os.environ.get('FFPANEL_TOKEN')
    if token:
        logger.info(f"Токен FFPanel найден в переменной окружения (длина: {len(token)})")
        # Маскируем токен для безопасности в логах
        masked_token = token[:4] + '*' * (len(token) - 8) + token[-4:]
        logger.info(f"Маскированный токен: {masked_token}")
        return token
    else:
        logger.error("Токен FFPanel не найден в переменной окружения")
        return None

def get_token_from_database():
    """Получает токен FFPanel из базы данных."""
    try:
        # Импортируем модели и устанавливаем контекст Flask
        from app import app
        from models import SystemSetting
        
        with app.app_context():
            token = SystemSetting.get_value('ffpanel_token')
            if token:
                logger.info(f"Токен FFPanel найден в базе данных (длина: {len(token)})")
                # Маскируем токен для безопасности в логах
                masked_token = token[:4] + '*' * (len(token) - 8) + token[-4:]
                logger.info(f"Маскированный токен: {masked_token}")
                return token
            else:
                logger.error("Токен FFPanel не найден в базе данных")
                return None
    except Exception as e:
        logger.error(f"Ошибка при получении токена из базы данных: {str(e)}")
        return None

def test_ffpanel_api_connection(token):
    """Тестирует подключение к FFPanel API с указанным токеном."""
    if not token:
        logger.error("Невозможно протестировать подключение: токен не предоставлен")
        return False
    
    try:
        import requests
        
        # URL для проверки аутентификации
        auth_url = "https://ffv2.ru/public/api"
        params = {
            'method': 'auth',
            'token': token
        }
        
        logger.info("Отправка запроса аутентификации к FFPanel API...")
        response = requests.get(auth_url, params=params)
        
        # Выводим результат
        if response.status_code == 200:
            data = response.json()
            if 'token' in data and 'jwt' in data['token']:
                jwt_token = data['token']['jwt']
                expire = data['token']['expire']
                logger.info(f"Аутентификация успешна! Получен JWT токен (длина: {len(jwt_token)})")
                logger.info(f"Срок действия токена: {datetime.fromtimestamp(expire)}")
                return True
            else:
                logger.error(f"Ошибка в структуре ответа API: {json.dumps(data)}")
                return False
        else:
            logger.error(f"Ошибка API: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Исключение при тестировании API: {str(e)}")
        return False

def test_get_sites(token):
    """Тестирует получение списка сайтов из FFPanel API."""
    if not token:
        logger.error("Невозможно получить список сайтов: токен не предоставлен")
        return False
    
    try:
        import requests
        
        # Сначала получаем JWT токен
        auth_url = "https://ffv2.ru/public/api"
        params = {
            'method': 'auth',
            'token': token
        }
        
        logger.info("Получение JWT токена...")
        auth_response = requests.get(auth_url, params=params)
        
        if auth_response.status_code != 200:
            logger.error(f"Ошибка аутентификации: {auth_response.status_code} - {auth_response.text}")
            return False
        
        auth_data = auth_response.json()
        if 'token' not in auth_data or 'jwt' not in auth_data['token']:
            logger.error(f"Ошибка в структуре ответа API: {json.dumps(auth_data)}")
            return False
        
        jwt_token = auth_data['token']['jwt']
        
        # Теперь получаем список сайтов
        api_url = "https://ffv2.ru/api/list.site"
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json'
        }
        
        logger.info("Получение списка сайтов...")
        sites_response = requests.get(api_url, headers=headers)
        
        if sites_response.status_code == 200:
            sites_data = sites_response.json()
            domains = sites_data.get('domains', [])
            
            logger.info(f"Успешно получен список сайтов (количество: {len(domains)})")
            if domains:
                # Выводим первые три домена для примера
                for i, domain in enumerate(domains[:3]):
                    logger.info(f"Домен {i+1}: {domain.get('domain')} (ID: {domain.get('id')})")
            return True
        elif sites_response.status_code == 404:
            logger.warning("Домены не найдены в FFPanel")
            return True
        else:
            logger.error(f"Ошибка получения списка сайтов: {sites_response.status_code} - {sites_response.text}")
            return False
    except Exception as e:
        logger.error(f"Исключение при получении списка сайтов: {str(e)}")
        return False

def update_token_in_database(token):
    """Обновляет токен FFPanel в базе данных."""
    if not token:
        logger.error("Невозможно обновить токен: не предоставлен токен")
        return False
    
    try:
        from app import app
        from models import SystemSetting, db
        
        with app.app_context():
            # Проверяем, существует ли запись
            setting = SystemSetting.query.filter_by(key='ffpanel_token').first()
            
            if setting:
                logger.info("Запись 'ffpanel_token' найдена в базе данных, обновляем...")
                SystemSetting.set_value('ffpanel_token', token, 'Токен API FFPanel', True)
                logger.info("Токен FFPanel успешно обновлен в базе данных")
            else:
                logger.info("Запись 'ffpanel_token' не найдена в базе данных, создаем новую...")
                SystemSetting.set_value('ffpanel_token', token, 'Токен API FFPanel', True)
                logger.info("Токен FFPanel успешно создан в базе данных")
            
            return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении токена в базе данных: {str(e)}")
        return False

def main():
    """Основная функция скрипта."""
    logger.info("=== Начало диагностики интеграции с FFPanel ===")
    
    # Получаем токен из переменной окружения
    env_token = get_token_from_environment()
    
    # Получаем токен из базы данных
    db_token = get_token_from_database()
    
    # Проверяем, совпадают ли токены
    if env_token and db_token:
        if env_token == db_token:
            logger.info("Токены в переменной окружения и базе данных совпадают")
        else:
            logger.warning("Токены в переменной окружения и базе данных различаются!")
            logger.info("Обновление токена в базе данных из переменной окружения...")
            update_token_in_database(env_token)
    elif env_token and not db_token:
        logger.warning("Токен найден только в переменной окружения, отсутствует в базе данных")
        logger.info("Сохраняем токен из переменной окружения в базу данных...")
        update_token_in_database(env_token)
    elif not env_token and db_token:
        logger.warning("Токен найден только в базе данных, отсутствует в переменной окружения")
    else:
        logger.error("Токен FFPanel не найден ни в переменной окружения, ни в базе данных!")
        logger.error("Невозможно протестировать интеграцию. Пожалуйста, установите токен.")
        return 1
    
    # Выбираем токен для тестирования API
    token_for_api = env_token or db_token
    
    # Проверяем соединение с API
    api_connection_ok = test_ffpanel_api_connection(token_for_api)
    
    if api_connection_ok:
        logger.info("Соединение с FFPanel API установлено успешно!")
        
        # Пробуем получить список сайтов
        sites_ok = test_get_sites(token_for_api)
        
        if sites_ok:
            logger.info("Получение списка сайтов из FFPanel выполнено успешно!")
        else:
            logger.error("Не удалось получить список сайтов из FFPanel")
    else:
        logger.error("Не удалось установить соединение с FFPanel API")
    
    logger.info("=== Завершение диагностики интеграции с FFPanel ===")
    
    return 0 if api_connection_ok else 1

if __name__ == "__main__":
    sys.exit(main())