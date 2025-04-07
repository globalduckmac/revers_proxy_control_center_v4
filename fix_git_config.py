#!/usr/bin/env python3
"""
Скрипт для настройки параметров git pull для предотвращения ошибок слияния.
Устанавливает опцию pull.rebase в false для использования стратегии слияния по умолчанию.

Для запуска:
python3 fix_git_config.py
или
python fix_git_config.py
"""
import subprocess
import sys

def configure_git_pull():
    """
    Настраивает параметры git pull для предотвращения ошибок слияния.
    """
    try:
        # Устанавливаем pull.rebase=false для использования стратегии слияния по умолчанию
        config_cmd = ['git', 'config', 'pull.rebase', 'false']
        result = subprocess.run(config_cmd, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            print(f"Ошибка при настройке git pull: {result.stderr.decode()}")
            return False
            
        print("Git pull успешно настроен для использования стратегии слияния по умолчанию.")
        
        # Дополнительно: настроим глобальное имя пользователя и email для коммитов
        # если они еще не настроены
        try:
            check_cmd = ['git', 'config', '--get', 'user.name']
            check_result = subprocess.run(check_cmd, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE)
            
            if not check_result.stdout.strip():
                # Имя пользователя не настроено, установим его
                user_cmd = ['git', 'config', 'user.name', 'RPCC System']
                subprocess.run(user_cmd)
                print("Установлено имя пользователя для git: RPCC System")
                
            check_cmd = ['git', 'config', '--get', 'user.email']
            check_result = subprocess.run(check_cmd, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE)
            
            if not check_result.stdout.strip():
                # Email не настроен, установим его
                email_cmd = ['git', 'config', 'user.email', 'admin@example.com']
                subprocess.run(email_cmd)
                print("Установлен email для git: admin@example.com")
        except Exception as e:
            print(f"Предупреждение при настройке имени пользователя и email: {e}")
            # Продолжаем выполнение, так как это не критическая ошибка
            
        return True
        
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return False

if __name__ == "__main__":
    success = configure_git_pull()
    sys.exit(0 if success else 1)