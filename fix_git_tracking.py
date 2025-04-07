#!/usr/bin/env python3
"""
Скрипт для настройки отслеживания удаленной ветки для текущей локальной ветки.
Устанавливает отслеживание удаленной ветки origin/main для локальной ветки main.

Для запуска:
python3 fix_git_tracking.py
или
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
        
        # Определяем URL репозитория
        repo_url = 'https://github.com/globalduckmac/revers_proxy_control_center_v4.git'
        
        # Проверяем, существует ли уже удаленный репозиторий origin
        remote_cmd = ['git', 'remote', 'get-url', 'origin']
        remote_result = subprocess.run(remote_cmd, 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE)
        
        if remote_result.returncode != 0:
            # Удаленный репозиторий не существует, добавляем его
            add_remote_cmd = ['git', 'remote', 'add', 'origin', repo_url]
            add_result = subprocess.run(add_remote_cmd, 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
            
            if add_result.returncode != 0:
                print(f"Ошибка при добавлении удаленного репозитория: {add_result.stderr.decode()}")
                return False
        else:
            # Удаленный репозиторий существует, проверяем URL
            current_url = remote_result.stdout.decode().strip()
            if current_url != repo_url:
                # URL отличается, обновляем его
                set_url_cmd = ['git', 'remote', 'set-url', 'origin', repo_url]
                set_result = subprocess.run(set_url_cmd, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE)
                
                if set_result.returncode != 0:
                    print(f"Ошибка при обновлении URL удаленного репозитория: {set_result.stderr.decode()}")
                    return False
        
        # Получаем последнюю информацию с удаленного репозитория
        fetch_cmd = ['git', 'fetch', 'origin']
        fetch_result = subprocess.run(fetch_cmd, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        
        if fetch_result.returncode != 0:
            print(f"Ошибка при получении информации с удаленного репозитория: {fetch_result.stderr.decode()}")
            return False
        
        # Устанавливаем отслеживание удаленной ветки
        track_cmd = ['git', 'branch', '--set-upstream-to=origin/main', current_branch]
        track_result = subprocess.run(track_cmd, 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        
        if track_result.returncode != 0:
            print(f"Ошибка при настройке отслеживания ветки: {track_result.stderr.decode()}")
            return False
        
        print(f"Успешно настроено отслеживание ветки origin/main для локальной ветки {current_branch}.")
        return True
    
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return False

if __name__ == "__main__":
    success = setup_branch_tracking()
    sys.exit(0 if success else 1)