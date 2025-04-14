#!/usr/bin/env python3
"""
Скрипт для диагностики и отладки интеграции с FFPanel API.
Проверяет подключение к FFPanel, настройки токена и возможность получения данных.

Запуск:
python debug_ffpanel_integration.py

Возможные аргументы:
--token TOKEN - Использовать указанный токен для тестирования вместо сохраненного
--verbose     - Подробный вывод, включая полные ответы API
--update      - Обновить токен в базе данных, если тестирование успешно
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime

from app import app, db
from models import SystemSetting, Domain


# Базовый URL для API FFPanel
FFPANEL_API_BASE_URL = "https://api.ffpanel.org/api"
FFPANEL_SITES_ENDPOINT = "/sites"


def get_token_from_environment():
    """Получает токен FFPanel из переменной окружения."""
    token = os.environ.get('FFPANEL_TOKEN')
    if token:
        print(f"[✓] Найден токен FFPanel в переменной окружения (длина: {len(token)})")
    else:
        print("[!] Токен FFPanel не найден в переменных окружения")
    return token


def get_token_from_database():
    """Получает токен FFPanel из базы данных."""
    try:
        with app.app_context():
            setting = SystemSetting.query.filter_by(key='ffpanel_token').first()
            if setting and setting.value:
                print(f"[✓] Найден токен FFPanel в базе данных (длина: {len(setting.value)})")
                return setting.value
            else:
                print("[!] Токен FFPanel не найден в базе данных")
                return None
    except Exception as e:
        print(f"[!] Ошибка при получении токена из базы данных: {str(e)}")
        return None


def test_ffpanel_api_connection(token, verbose=False):
    """Тестирует подключение к FFPanel API с указанным токеном."""
    if not token:
        print("[!] Ошибка: Токен не указан")
        return False
    
    print("\n=== Тестирование подключения к FFPanel API ===")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    try:
        # Тестируем получение информации об аккаунте
        url = f"{FFPANEL_API_BASE_URL}/account"
        print(f"[*] Запрос к {url}")
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[✓] Подключение успешно! Статус: {response.status_code}")
            
            if verbose:
                print("\nПолный ответ:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print(f"[i] Аккаунт: {data.get('data', {}).get('company_name', 'Н/Д')}")
                print(f"[i] Email: {data.get('data', {}).get('email', 'Н/Д')}")
            
            return True
        else:
            print(f"[!] Ошибка подключения. Статус: {response.status_code}")
            print(f"[!] Ответ: {response.text}")
            return False
    
    except Exception as e:
        print(f"[!] Ошибка при подключении к FFPanel API: {str(e)}")
        return False


def test_get_sites(token, verbose=False):
    """Тестирует получение списка сайтов из FFPanel API."""
    if not token:
        print("[!] Ошибка: Токен не указан")
        return False
    
    print("\n=== Получение списка сайтов из FFPanel API ===")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    try:
        url = f"{FFPANEL_API_BASE_URL}{FFPANEL_SITES_ENDPOINT}"
        print(f"[*] Запрос к {url}")
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            sites = data.get('data', [])
            
            print(f"[✓] Получено {len(sites)} сайтов")
            
            if verbose and sites:
                print("\nПервые 5 сайтов:")
                for i, site in enumerate(sites[:5]):
                    print(f"\n--- Сайт {i+1} ---")
                    print(f"ID: {site.get('id')}")
                    print(f"Домен: {site.get('domain')}")
                    print(f"Статус: {site.get('status')}")
            else:
                print("\nПроверка сопоставления с базой данных:")
                check_domain_matching(sites)
            
            return True
        else:
            print(f"[!] Ошибка получения списка сайтов. Статус: {response.status_code}")
            print(f"[!] Ответ: {response.text}")
            return False
    
    except Exception as e:
        print(f"[!] Ошибка при получении списка сайтов: {str(e)}")
        return False


def check_domain_matching(ffpanel_sites):
    """Проверяет, сколько доменов из FFPanel есть в базе данных."""
    try:
        with app.app_context():
            ffpanel_domains = {site.get('domain'): site.get('id') for site in ffpanel_sites}
            
            # Получаем все домены из базы данных
            domains = Domain.query.all()
            
            # Подсчитываем совпадения
            matched = 0
            mismatched_ids = 0
            
            for domain in domains:
                if domain.name in ffpanel_domains:
                    matched += 1
                    # Проверяем совпадение ID
                    if domain.ffpanel_id and domain.ffpanel_id != ffpanel_domains[domain.name]:
                        mismatched_ids += 1
            
            print(f"[i] В базе данных найдено {len(domains)} доменов")
            print(f"[i] В FFPanel API найдено {len(ffpanel_domains)} доменов")
            print(f"[i] Совпадающих доменов: {matched} из {len(domains)}")
            
            if mismatched_ids > 0:
                print(f"[!] Внимание: {mismatched_ids} доменов имеют несовпадающие ffpanel_id")
            
            # Выводим статистику по ffpanel_enabled
            enabled = Domain.query.filter_by(ffpanel_enabled=True).count()
            print(f"[i] Доменов с включенной опцией ffpanel_enabled: {enabled} из {len(domains)}")
            
    except Exception as e:
        print(f"[!] Ошибка при проверке сопоставления доменов: {str(e)}")


def update_token_in_database(token):
    """Обновляет токен FFPanel в базе данных."""
    try:
        with app.app_context():
            setting = SystemSetting.query.filter_by(key='ffpanel_token').first()
            
            if setting:
                setting.value = token
                print("[✓] Токен FFPanel обновлен в базе данных")
            else:
                setting = SystemSetting(key='ffpanel_token', value=token, description='Токен авторизации FFPanel API')
                db.session.add(setting)
                print("[✓] Токен FFPanel добавлен в базу данных")
            
            db.session.commit()
            return True
    except Exception as e:
        print(f"[!] Ошибка при обновлении токена в базе данных: {str(e)}")
        return False


def main():
    """Основная функция скрипта."""
    parser = argparse.ArgumentParser(description='Диагностика интеграции с FFPanel API')
    parser.add_argument('--token', help='Токен FFPanel API для тестирования')
    parser.add_argument('--verbose', action='store_true', help='Подробный вывод')
    parser.add_argument('--update', action='store_true', help='Обновить токен в базе данных')
    args = parser.parse_args()
    
    print("=== Диагностика интеграции с FFPanel API ===")
    print(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Получение токена из разных источников
    token_env = get_token_from_environment()
    token_db = get_token_from_database()
    token_arg = args.token

    # Определение токена для использования
    token = token_arg or token_env or token_db
    
    if not token:
        print("\n[!] Ошибка: Токен FFPanel не найден ни в одном из источников")
        print("[i] Укажите токен через аргумент --token или установите переменную окружения FFPANEL_TOKEN")
        return False
    
    source = "аргумента командной строки" if token_arg else ("переменной окружения" if token == token_env else "базы данных")
    print(f"\n[i] Используется токен из {source}")
    
    # Проверка соединения
    connection_ok = test_ffpanel_api_connection(token, args.verbose)
    
    if connection_ok:
        # Проверка получения сайтов
        sites_ok = test_get_sites(token, args.verbose)
        
        # Обновление токена в базе данных, если запрошено
        if args.update and token_arg and sites_ok:
            update_token_in_database(token_arg)
        
        print("\n=== Итог диагностики ===")
        print("[✓] Подключение к FFPanel API: Успешно")
        print(f"[{'✓' if sites_ok else '✗'}] Получение списка сайтов: {'Успешно' if sites_ok else 'Ошибка'}")
        
        if token_env and token_db and token_env != token_db:
            print("\n[!] Внимание: Токены в переменной окружения и базе данных не совпадают!")
            print("[i] Рекомендуется обновить токен в базе данных с помощью скрипта update_ffpanel_token.py")
        
        return True
    else:
        print("\n=== Итог диагностики ===")
        print("[✗] Диагностика не удалась: проблемы с подключением к FFPanel API")
        return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)