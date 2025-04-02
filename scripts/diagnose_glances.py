#!/usr/bin/env python3

"""
Скрипт для диагностики Glances API на сервере.
Проверяет доступность API и его основные функции.

Использование:
python3 diagnose_glances.py <ip-адрес> [порт]

По умолчанию порт: 61208
"""

import sys
import requests
import json
from datetime import datetime

def check_glances_api(host, port=61208):
    """
    Проверяет доступность и работоспособность Glances API на указанном хосте и порту.
    
    Args:
        host (str): IP-адрес или домен сервера с Glances
        port (int): Порт Glances Web API (по умолчанию 61208)
        
    Returns:
        bool: True если API доступен и работает, False в противном случае
    """
    base_url = f"http://{host}:{port}"
    
    print(f"Проверка Glances API на {base_url}...")
    
    # Проверяем доступность API
    try:
        # Проверяем версию API
        response = requests.get(f"{base_url}/api", timeout=5)
        if response.status_code == 200:
            versions = response.json()
            print(f"Доступные версии API: {', '.join(map(str, versions))}")
            if 4 not in versions:
                print("ВНИМАНИЕ: Рекомендуемая версия API 4 не найдена!")
        else:
            print(f"Ошибка при запросе /api: {response.status_code}")
            return False
        
        # Получаем все данные
        response = requests.get(f"{base_url}/api/4/all", timeout=5)
        if response.status_code != 200:
            print(f"Ошибка при запросе /api/4/all: {response.status_code}")
            return False
        
        data = response.json()
        
        # Проверяем основные метрики
        print("\nПроверка основных метрик:")
        
        # CPU
        if 'cpu' in data:
            cpu_percent = data['cpu'].get('total', {}).get('user', 0)
            print(f"CPU загрузка: {cpu_percent}%")
        else:
            print("ОШИБКА: Данные о CPU не найдены!")
        
        # Memory
        if 'mem' in data:
            memory_percent = data['mem'].get('percent', 0)
            print(f"Использование памяти: {memory_percent}%")
        else:
            print("ОШИБКА: Данные о памяти не найдены!")
        
        # Disk
        if 'fs' in data and len(data['fs']) > 0:
            for fs in data['fs']:
                if fs.get('mnt_point') == '/':
                    disk_percent = fs.get('percent', 0)
                    print(f"Использование диска /: {disk_percent}%")
                    break
        else:
            print("ОШИБКА: Данные о дисках не найдены!")
        
        # Load
        if 'load' in data:
            load_avg = data['load'].get('min5', 0)
            print(f"Средняя нагрузка (5 мин): {load_avg}")
        else:
            print("ОШИБКА: Данные о нагрузке не найдены!")
        
        # Uptime
        if 'uptime' in data:
            uptime = data['uptime']
            print(f"Время работы сервера: {uptime}")
        else:
            print("ОШИБКА: Данные о времени работы не найдены!")
        
        # Проверка на дополнительные метрики
        print("\nПроверка дополнительных метрик:")
        
        # Network
        if 'network' in data and len(data['network']) > 0:
            interfaces = [net.get('interface') for net in data['network'] 
                        if net.get('interface') not in ['lo', 'total']]
            print(f"Сетевые интерфейсы: {', '.join(interfaces)}")
        else:
            print("ВНИМАНИЕ: Данные о сетевых интерфейсах не найдены или отключены!")
        
        # Processes
        if 'processcount' in data:
            process_count = data['processcount'].get('total', 0)
            print(f"Всего процессов: {process_count}")
        else:
            print("ВНИМАНИЕ: Данные о процессах не найдены или отключены!")
        
        print("\nДиагностика Glances API успешно завершена!")
        return True
        
    except requests.exceptions.ConnectionError:
        print(f"ОШИБКА: Не удалось подключиться к {base_url}")
        print("Проверьте, что Glances установлен и запущен на сервере.")
        print("Рекомендации:")
        print("1. Убедитесь, что сервис запущен: 'sudo systemctl status glances'")
        print("2. Проверьте файрвол: 'sudo ufw status' или 'sudo iptables -L'")
        print("3. Перезапустите сервис: 'sudo systemctl restart glances'")
        return False
    except requests.exceptions.Timeout:
        print(f"ОШИБКА: Таймаут при подключении к {base_url}")
        return False
    except Exception as e:
        print(f"ОШИБКА: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Использование: {sys.argv[0]} <ip-адрес> [порт]")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 61208
    
    if not check_glances_api(host, port):
        sys.exit(1)
    
    sys.exit(0)