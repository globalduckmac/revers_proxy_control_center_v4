#!/usr/bin/env python3
"""
Скрипт для тестирования обновленного класса FFPanelAPI.
Этот скрипт может работать за пределами контекста Flask
и использует настроенный собственный логгер.

Для запуска:
python test_ffpanel_api.py
"""

import os
import sys
import logging
from modules.ffpanel_api import FFPanelAPI

def setup_logger():
    """Настройка логгера для вывода в консоль"""
    logger = logging.getLogger('test_ffpanel')
    logger.setLevel(logging.DEBUG)
    
    # Создаем обработчик для вывода в консоль
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)
    
    logger.addHandler(handler)
    return logger

def main():
    """Основная функция для тестирования FFPanelAPI"""
    logger = setup_logger()
    logger.info("Запуск тестирования FFPanelAPI")
    
    # Инициализируем клиент API с нашим логгером
    api = FFPanelAPI(logger=logger)
    
    # Проверяем токен
    logger.info(f"Найден токен FFPanel: {'Да' if api.token else 'Нет'}")
    
    # Если токен не найден, пробуем использовать переменную окружения
    if not api.token:
        token = os.environ.get('FFPANEL_TOKEN')
        if token:
            logger.info(f"Используем токен из переменной окружения FFPANEL_TOKEN")
            api = FFPanelAPI(token=token, logger=logger)
        else:
            logger.error("Токен FFPanel не найден ни в базе данных, ни в переменных окружения.")
            logger.error("Установите переменную окружения FFPANEL_TOKEN или добавьте токен в настройки системы.")
            return 1
    
    # Проверяем аутентификацию
    logger.info("Проверка аутентификации...")
    auth_result = api._authenticate()
    logger.info(f"Результат аутентификации: {'Успешно' if auth_result else 'Ошибка'}")
    
    if not auth_result:
        logger.error("Не удалось аутентифицироваться с FFPanel API. Проверьте токен.")
        return 1
    
    # Получаем список сайтов
    logger.info("Запрос списка сайтов...")
    sites = api.get_sites()
    logger.info(f"Получено {len(sites)} сайтов из FFPanel")
    
    # Выводим первые 5 сайтов для проверки
    if sites:
        logger.info("Первые 5 сайтов:")
        for i, site in enumerate(sites[:5], 1):
            logger.info(f"{i}. ID: {site.get('id')}, Домен: {site.get('domain')}, IP: {site.get('ip_path')}")
    
    logger.info("Тестирование FFPanelAPI завершено успешно")
    return 0

if __name__ == "__main__":
    sys.exit(main())