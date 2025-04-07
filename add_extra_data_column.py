#!/usr/bin/env python
"""
Скрипт для добавления поля extra_data в таблицу ProxyConfig

Этот скрипт можно запустить из любой директории, так как он 
не зависит от импорта модулей приложения.

Для запуска:
python3 add_extra_data_column.py

Необходимо указать переменную DATABASE_URL в окружении или в файле .env
"""

import os
import sys
import psycopg2
from psycopg2 import sql

# Получаем URL базы данных из переменной окружения
DATABASE_URL = os.environ.get('DATABASE_URL')

# Если DATABASE_URL не найден в окружении, пытаемся прочитать из файла .env
if not DATABASE_URL:
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    DATABASE_URL = line.split('=', 1)[1].strip()
                    break

# Если DATABASE_URL всё ещё не найден, запрашиваем у пользователя
if not DATABASE_URL:
    print("Не найден DATABASE_URL в переменных окружения или в файле .env")
    DATABASE_URL = input("Введите URL базы данных PostgreSQL: ")

def add_extra_data_column():
    """
    Добавляет столбец extra_data в таблицу proxy_config, если он еще не существует
    """
    try:
        # Устанавливаем соединение с базой данных
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cursor = conn.cursor()
        
        print(f"Соединение с базой данных установлено.")
        
        # Проверяем, существует ли уже колонка extra_data
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='proxy_config' AND column_name='extra_data';
        """)
        
        if cursor.fetchone():
            print("Колонка extra_data уже существует в таблице proxy_config.")
            return True
            
        # Добавляем колонку extra_data
        cursor.execute("""
            ALTER TABLE proxy_config ADD COLUMN extra_data TEXT NULL;
        """)
        
        print("Колонка extra_data успешно добавлена в таблицу proxy_config.")
        return True
        
    except Exception as e:
        print(f"Ошибка: {str(e)}")
        return False
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            print("Соединение с базой данных закрыто.")

if __name__ == "__main__":
    print("Запуск миграции для добавления поля extra_data в таблицу proxy_config...")
    
    if add_extra_data_column():
        print("Миграция успешно завершена.")
        sys.exit(0)
    else:
        print("Ошибка при выполнении миграции.")
        sys.exit(1)