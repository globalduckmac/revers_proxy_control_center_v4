#!/usr/bin/env python3
"""
Скрипт для автоматического обновления кода с GitHub.
Решает проблемы с git pull, настраивает отслеживание веток и выполняет обновление.

Для запуска:
python update_from_github.py
"""
import os
import subprocess
import sys
import time

def run_script(script_name):
    """
    Запускает указанный Python-скрипт и возвращает результат выполнения.
    
    Args:
        script_name: Имя скрипта для запуска (без расширения .py)
        
    Returns:
        bool: True если скрипт выполнен успешно, False в случае ошибки
    """
    try:
        # Пробуем сначала с python3, затем с python (для обратной совместимости)
        try:
            result = subprocess.run(['python3', f'{script_name}.py'], 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE)
        except FileNotFoundError:
            # Если python3 не найден, пробуем с python
            result = subprocess.run(['python', f'{script_name}.py'], 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE)
        
        # Выводим результаты выполнения скрипта
        if result.stdout:
            print(result.stdout.decode())
        
        if result.stderr:
            print(result.stderr.decode())
        
        return result.returncode == 0
    except Exception as e:
        print(f"Ошибка при запуске скрипта {script_name}.py: {e}")
        return False

def update_from_github():
    """
    Выполняет автоматическое обновление кода с GitHub.
    
    Returns:
        bool: True если обновление выполнено успешно, False в случае ошибки
    """
    try:
        print("Шаг 1: Настройка параметров git pull...")
        if not run_script('fix_git_config'):
            print("Ошибка при настройке параметров git pull. Пробуем продолжить...")
        
        print("\nШаг 2: Настройка отслеживания удаленной ветки...")
        if not run_script('fix_git_tracking'):
            print("Ошибка при настройке отслеживания ветки. Пробуем продолжить с принудительным сбросом...")
            print("\nШаг 2 (альтернативно): Принудительный сброс до состояния удаленного репозитория...")
            if not run_script('git_auto_reset'):
                print("Ошибка при принудительном сбросе. Прерываем обновление.")
                return False
        
        print("\nШаг 3: Выполнение git pull для получения последних изменений...")
        try:
            pull_cmd = ['git', 'pull']
            pull_result = subprocess.run(pull_cmd, 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE)
            
            if pull_result.returncode != 0:
                print(f"Ошибка при выполнении git pull: {pull_result.stderr.decode()}")
                
                print("\nПробуем альтернативный метод с принудительным сбросом...")
                if not run_script('git_auto_reset'):
                    print("Ошибка при принудительном сбросе. Прерываем обновление.")
                    return False
            else:
                print(pull_result.stdout.decode())
                
            # Перезапуск веб-сервера (по необходимости)
            print("\nШаг 4: Перезапуск веб-сервера (если необходимо)...")
            # Здесь можно добавить код для перезапуска сервера, если это требуется
            
            print("\nОбновление успешно завершено!")
            return True
            
        except Exception as e:
            print(f"Ошибка при выполнении git pull: {e}")
            return False
            
    except Exception as e:
        print(f"Произошла ошибка в процессе обновления: {e}")
        return False

if __name__ == "__main__":
    print("=== Автоматическое обновление кода с GitHub ===")
    print(f"Дата и время запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 45)
    
    success = update_from_github()
    sys.exit(0 if success else 1)