#!/usr/bin/env python3
"""
Скрипт для синхронизации токена FFPanel из переменной окружения с системными настройками приложения.
Этот скрипт напрямую подключается к базе данных, чтобы обойти проблемы с циклическими импортами.

python3 update_ffpanel_token_direct.py
"""

import os
import sys
from sqlalchemy import create_engine, MetaData, Table, select, update
from sqlalchemy.orm import sessionmaker

def update_ffpanel_token():
    # Получаем токен из переменной окружения
    ffpanel_token = os.environ.get('FFPANEL_TOKEN')
    
    if not ffpanel_token:
        print("Ошибка: Переменная окружения FFPANEL_TOKEN не найдена")
        return False
    
    # Получаем строку подключения к базе данных
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("Ошибка: Переменная окружения DATABASE_URL не найдена")
        return False
    
    try:
        # Подключаемся к базе данных
        engine = create_engine(database_url)
        connection = engine.connect()
        
        # Создаем метаданные и ссылку на таблицу system_setting
        metadata = MetaData()
        system_setting = Table('system_setting', metadata, autoload_with=engine)
        
        # Проверяем, существует ли запись с ключом ffpanel_token
        query = select(system_setting).where(system_setting.c.key == 'ffpanel_token')
        result = connection.execute(query).fetchone()
        
        if result:
            # Если запись существует, обновляем её
            stmt = update(system_setting).where(system_setting.c.key == 'ffpanel_token').values(value=ffpanel_token)
            connection.execute(stmt)
            print(f"Успешно: Токен FFPanel обновлен, длина: {len(ffpanel_token)}")
        else:
            # Если записи нет, вставляем новую
            stmt = system_setting.insert().values(
                key='ffpanel_token',
                value=ffpanel_token,
                description='Токен API FFPanel',
                is_encrypted=True
            )
            connection.execute(stmt)
            print(f"Успешно: Токен FFPanel добавлен, длина: {len(ffpanel_token)}")
        
        connection.commit()
        connection.close()
        return True
    except Exception as e:
        print(f"Ошибка при обновлении токена FFPanel: {str(e)}")
        return False

if __name__ == "__main__":
    update_ffpanel_token()