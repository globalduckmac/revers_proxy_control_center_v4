#!/usr/bin/env python3
"""
Скрипт для автоматического сброса локального репозитория к состоянию удаленного репозитория.
Используется, когда локальная и удаленная ветки разошлись, и git pull не может автоматически их согласовать.

Для запуска:
python git_auto_reset.py
"""
import os
import subprocess
import sys

def reset_to_remote():
    """
    Автоматически сбрасывает локальный репозиторий к состоянию удаленного репозитория.
    """
    try:
        # Получаем последнюю информацию с удаленного репозитория
        fetch_cmd = ['git', 'fetch', 'origin', 'main']
        result = subprocess.run(fetch_cmd, 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            print(f"Ошибка при получении информации с удаленного репозитория: {result.stderr.decode()}")
            return False
            
        # Сбросить локальную ветку до состояния FETCH_HEAD (последнее состояние удаленной ветки)
        reset_cmd = ['git', 'reset', '--hard', 'FETCH_HEAD']
        result = subprocess.run(reset_cmd, 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            print(f"Ошибка при сбросе локального репозитория: {result.stderr.decode()}")
            return False
            
        print("Локальный репозиторий успешно сброшен до состояния удаленного репозитория.")
        return True
        
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return False

if __name__ == "__main__":
    # Автоматический сброс без запроса подтверждения
    success = reset_to_remote()
    sys.exit(0 if success else 1)