#!/usr/bin/env python3
"""
Скрипт для обновления токена FFPanel в настройках системы.
Источником токена может быть переменная окружения FFPANEL_TOKEN или аргумент командной строки.

Запуск:
python update_ffpanel_token.py [токен]

Если токен не указан в аргументе, скрипт попытается получить его из переменной окружения FFPANEL_TOKEN.
Если токен не найден ни в аргументе, ни в переменной окружения, скрипт запросит его у пользователя.
"""

import os
import sys
import argparse
from app import app, db
from models import SystemSetting


def update_ffpanel_token_in_db(token):
    """
    Обновляет токен FFPanel в таблице системных настроек
    
    Args:
        token (str): Токен FFPanel API
        
    Returns:
        bool: True если токен успешно обновлен, False в случае ошибки
    """
    try:
        with app.app_context():
            # Поиск настройки ffpanel_token
            setting = SystemSetting.query.filter_by(key='ffpanel_token').first()
            
            if setting:
                # Обновление существующей настройки
                setting.value = token
                print(f"Токен FFPanel обновлен (длина: {len(token)})")
            else:
                # Создание новой настройки
                setting = SystemSetting(key='ffpanel_token', value=token, description='Токен авторизации FFPanel API')
                db.session.add(setting)
                print(f"Токен FFPanel создан (длина: {len(token)})")
                
            db.session.commit()
            return True
    except Exception as e:
        print(f"Ошибка при обновлении токена FFPanel: {str(e)}")
        return False


def get_token_from_environment():
    """
    Получает токен FFPanel из переменной окружения
    
    Returns:
        str: Токен FFPanel или None, если переменная не установлена
    """
    token = os.environ.get('FFPANEL_TOKEN')
    if token:
        print(f"Найден токен FFPanel в переменной окружения (длина: {len(token)})")
    else:
        print("Токен FFPanel не найден в переменных окружения")
    return token


def get_token_from_user():
    """
    Запрашивает токен FFPanel у пользователя
    
    Returns:
        str: Токен FFPanel, введенный пользователем
    """
    print("\nВведите токен FFPanel API:")
    token = input("> ").strip()
    return token if token else None


def main():
    """
    Основная функция скрипта
    """
    parser = argparse.ArgumentParser(description='Обновление токена FFPanel API')
    parser.add_argument('token', nargs='?', help='Токен FFPanel API (необязательно)')
    args = parser.parse_args()
    
    # Получение токена из аргумента, переменной окружения или от пользователя
    token = args.token or get_token_from_environment() or get_token_from_user()
    
    if not token:
        print("Ошибка: Токен FFPanel не указан")
        return False
    
    # Обновление токена в базе данных
    if update_ffpanel_token_in_db(token):
        print("\nТокен FFPanel успешно обновлен в базе данных")
        
        # Проверка, установлена ли переменная окружения
        if not os.environ.get('FFPANEL_TOKEN'):
            print("\nРекомендация: Для постоянного использования, добавьте переменную окружения:")
            print("export FFPANEL_TOKEN=\"" + token + "\"")
            print("или добавьте эту строку в файл ~/.bashrc или ~/.profile")
        return True
    else:
        print("\nОшибка: Не удалось обновить токен FFPanel в базе данных")
        return False


if __name__ == "__main__":
    sys.exit(0 if main() else 1)