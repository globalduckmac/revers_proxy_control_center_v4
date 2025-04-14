#!/usr/bin/env python3
"""
Скрипт для синхронизации токена FFPanel из переменной окружения с системными настройками приложения.
Запускать в той же директории, где находится приложение.

python3 update_ffpanel_token.py
"""

import os
import sys
from models import SystemSetting, db
from app import app

def update_ffpanel_token():
    # Получаем токен из переменной окружения
    ffpanel_token = os.environ.get('FFPANEL_TOKEN')
    
    if not ffpanel_token:
        print("Ошибка: Переменная окружения FFPANEL_TOKEN не найдена")
        return False
    
    # Создаем контекст приложения, чтобы работать с базой данных
    with app.app_context():
        # Обновляем токен в базе данных
        SystemSetting.set_value(
            'ffpanel_token', 
            ffpanel_token, 
            'Токен API FFPanel', 
            True  # шифровать значение
        )
        
        # Проверяем, что токен установлен
        updated_token = SystemSetting.get_value('ffpanel_token')
        if updated_token == ffpanel_token:
            print(f"Успешно: Токен FFPanel обновлен, длина: {len(ffpanel_token)}")
            return True
        else:
            print("Ошибка: Не удалось обновить токен FFPanel")
            return False

if __name__ == "__main__":
    update_ffpanel_token()