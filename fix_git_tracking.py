#!/usr/bin/env python3
"""
Скрипт для настройки отслеживания удаленной ветки для текущей локальной ветки.
Устанавливает отслеживание удаленной ветки github_v4/main для локальной ветки main.

Для запуска:
python fix_git_tracking.py
"""
import os
import subprocess
import sys

def setup_branch_tracking():
    """
    Настраивает отслеживание удаленной ветки для текущей локальной ветки.
    """
    try:
        # Проверяем, какая ветка сейчас активна
        branch_cmd = ['git', 'branch', '--show-current']
        branch_result = subprocess.run(branch_cmd, 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE)
        
        if branch_result.returncode != 0:
            print(f"Ошибка при определении текущей ветки: {branch_result.stderr.decode()}")
            return False
        
        current_branch = branch_result.stdout.decode().strip()
        if not current_branch:
            print("Не удалось определить текущую ветку.")
            return False
        
        # Получаем GITHUB_TOKEN для доступа к удаленному репозиторию
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            print("GITHUB_TOKEN не найден в переменных окружения!")
            return False
        
        # Создаем/обновляем удаленный репозиторий
        remote_url = f'https://{token}@github.com/globalduckmac/revers_proxy_control_center_v4.git'
        
        # Проверяем, существует ли уже удаленный репозиторий github_v4
        remote_cmd = ['git', 'remote', 'get-url', 'github_v4']
        remote_result = subprocess.run(remote_cmd, 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE)
        
        if remote_result.returncode != 0:
            # Удаленный репозиторий не существует, добавляем его
            add_remote_cmd = ['git', 'remote', 'add', 'github_v4', remote_url]
            add_result = subprocess.run(add_remote_cmd, 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
            
            if add_result.returncode != 0:
                print(f"Ошибка при добавлении удаленного репозитория: {add_result.stderr.decode()}")
                return False
        else:
            # Удаленный репозиторий существует, обновляем URL
            set_url_cmd = ['git', 'remote', 'set-url', 'github_v4', remote_url]
            set_result = subprocess.run(set_url_cmd, 
                             stdout=subprocess.PIPE, 
                             stderr=subprocess.PIPE)
            
            if set_result.returncode != 0:
                print(f"Ошибка при обновлении URL удаленного репозитория: {set_result.stderr.decode()}")
                return False
        
        # Получаем последнюю информацию с удаленного репозитория
        fetch_cmd = ['git', 'fetch', 'github_v4']
        fetch_result = subprocess.run(fetch_cmd, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        
        if fetch_result.returncode != 0:
            print(f"Ошибка при получении информации с удаленного репозитория: {fetch_result.stderr.decode()}")
            return False
        
        # Устанавливаем отслеживание удаленной ветки
        track_cmd = ['git', 'branch', '--set-upstream-to=github_v4/main', current_branch]
        track_result = subprocess.run(track_cmd, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        
        if track_result.returncode != 0:
            print(f"Ошибка при настройке отслеживания ветки: {track_result.stderr.decode()}")
            return False
        
        print(f"Успешно настроено отслеживание ветки github_v4/main для локальной ветки {current_branch}.")
        return True
    
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return False

if __name__ == "__main__":
    success = setup_branch_tracking()
    sys.exit(0 if success else 1)