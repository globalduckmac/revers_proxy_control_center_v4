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


# Базовый URL для API FFPanel (должен совпадать с URL в modules/ffpanel_api.py)
FFPANEL_API_BASE_URL = "https://ffv2.ru/api"
FFPANEL_AUTH_URL = "https://ffv2.ru/public/api"
FFPANEL_SITES_ENDPOINT = ""  # Endpoint уже включен в URL вызовов в коде


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
    
    try:
        # Аутентификация через auth метод (как в FFPanelAPI._authenticate)
        url = f"{FFPANEL_AUTH_URL}"
        params = {
            'method': 'auth',
            'token': token
        }
        print(f"[*] Запрос аутентификации к {url}")
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'token' in data:
                jwt_token = data['token']['jwt']
                jwt_expire = data['token']['expire']
                print(f"[✓] Аутентификация успешна! JWT токен получен (истекает: {datetime.fromtimestamp(jwt_expire)})")
                
                # Теперь используем JWT для проверки запроса к API
                headers = {
                    "Authorization": f"Bearer {jwt_token}",
                    "Content-Type": "application/json"
                }
                
                # Проверяем API запросом list.site (как в FFPanelAPI.get_sites)
                list_url = f"{FFPANEL_API_BASE_URL}/list.site"
                print(f"[*] Запрос списка сайтов к {list_url}")
                
                list_response = requests.get(list_url, headers=headers)
                
                if list_response.status_code == 200:
                    sites_data = list_response.json()
                    domains_count = len(sites_data.get('domains', []))
                    print(f"[✓] Подключение к API успешно! Получено {domains_count} доменов")
                    
                    if verbose:
                        print("\nПервые 5 доменов:")
                        for i, domain in enumerate(sites_data.get('domains', [])[:5]):
                            print(f"{i+1}. ID: {domain.get('id')}, Домен: {domain.get('domain')}")
                    
                    return True
                else:
                    print(f"[!] Аутентификация успешна, но запрос к API не удался. Статус: {list_response.status_code}")
                    print(f"[!] Ответ: {list_response.text}")
                    return False
            else:
                print(f"[!] Ошибка аутентификации. Токен не найден в ответе.")
                print(f"[!] Ответ: {response.text}")
                return False
        else:
            print(f"[!] Ошибка аутентификации. Статус: {response.status_code}")
            print(f"[!] Ответ: {response.text}")
            return False
    
    except Exception as e:
        print(f"[!] Ошибка при подключении к FFPanel API: {str(e)}")
        return False


def get_jwt_token(token):
    """Получает JWT токен через аутентификацию."""
    try:
        url = f"{FFPANEL_AUTH_URL}"
        params = {
            'method': 'auth',
            'token': token
        }
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if 'token' in data:
                return data['token']['jwt']
        return None
    except Exception:
        return None


def test_get_sites(token, verbose=False):
    """Тестирует получение списка сайтов из FFPanel API."""
    if not token:
        print("[!] Ошибка: Токен не указан")
        return False
    
    print("\n=== Получение списка сайтов из FFPanel API ===")
    
    # Сначала получаем JWT токен
    jwt_token = get_jwt_token(token)
    if not jwt_token:
        print("[!] Ошибка: Не удалось получить JWT токен для запроса сайтов")
        return False
    
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    
    try:
        url = f"{FFPANEL_API_BASE_URL}/list.site"
        print(f"[*] Запрос к {url}")
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            domains = data.get('domains', [])
            
            print(f"[✓] Получено {len(domains)} сайтов")
            
            if verbose and domains:
                print("\nПервые 5 сайтов:")
                for i, domain in enumerate(domains[:5]):
                    print(f"\n--- Сайт {i+1} ---")
                    print(f"ID: {domain.get('id')}")
                    print(f"Домен: {domain.get('domain')}")
                    print(f"IP: {domain.get('ip_path')}")
            else:
                print("\nПроверка сопоставления с базой данных:")
                check_domain_matching(domains)
            
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