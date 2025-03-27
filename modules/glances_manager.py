"""
Модуль для взаимодействия с Glances API.
"""

import logging
import requests
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class GlancesAPI:
    """
    Класс для взаимодействия с Glances API.
    
    Предоставляет методы для получения метрик и состояния сервера
    через Glances API (версия 4).
    """
    
    def __init__(self, host, port=61208, timeout=5, api_version=4):
        """
        Инициализация клиента Glances API.
        
        Args:
            host (str): Хост или IP-адрес сервера.
            port (int, optional): Порт Glances API. По умолчанию 61208.
            timeout (int, optional): Таймаут подключения в секундах. По умолчанию 5.
            api_version (int, optional): Версия API Glances. По умолчанию 4.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.api_version = api_version
        self.base_url = f"http://{host}:{port}/api/{api_version}"
    
    def _make_request(self, endpoint):
        """
        Выполняет HTTP-запрос к API Glances.
        
        Args:
            endpoint (str): Конечная точка API (без слеша в начале).
            
        Returns:
            dict: Данные от API в формате JSON или None в случае ошибки.
        """
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Ошибка соединения с Glances API на сервере {self.host}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Неизвестная ошибка при обращении к Glances API на сервере {self.host}: {str(e)}")
            return None
    
    def is_available(self):
        """
        Проверяет доступность Glances API.
        
        Returns:
            bool: True, если API доступно, иначе False.
        """
        # Используем CPU как простой эндпоинт для проверки доступности
        data = self._make_request("cpu")
        return data is not None
    
    def get_cpu_info(self):
        """
        Получает информацию о загрузке CPU.
        
        Returns:
            dict: Информация о загрузке CPU или None в случае ошибки.
        """
        return self._make_request("cpu")
    
    def get_memory_info(self):
        """
        Получает информацию об использовании памяти.
        
        Returns:
            dict: Информация об использовании памяти или None в случае ошибки.
        """
        return self._make_request("mem")
    
    def get_disk_info(self):
        """
        Получает информацию об использовании дисков.
        
        Returns:
            dict: Информация об использовании дисков или None в случае ошибки.
        """
        return self._make_request("fs")
    
    def get_network_info(self):
        """
        Получает информацию о сетевой активности.
        
        Returns:
            dict: Информация о сетевой активности или None в случае ошибки.
        """
        return self._make_request("network")
    
    def get_process_info(self):
        """
        Получает информацию о запущенных процессах.
        
        Returns:
            dict: Информация о запущенных процессах или None в случае ошибки.
        """
        return self._make_request("process")
    
    def get_system_info(self):
        """
        Получает общую информацию о системе.
        
        Returns:
            dict: Общая информация о системе или None в случае ошибки.
        """
        return self._make_request("system")
    
    def get_all_metrics(self):
        """
        Получает все основные метрики сервера.
        
        Returns:
            dict: Словарь со всеми метриками или None в случае ошибки.
                Ключи: 'cpu', 'memory', 'disk', 'network', 'system'.
        """
        # Проверяем доступность API перед запросом всех метрик
        if not self.is_available():
            logger.warning(f"Glances API недоступен на сервере {self.host}")
            return None
        
        metrics = {
            'cpu': self.get_cpu_info(),
            'memory': self.get_memory_info(),
            'disk': self.get_disk_info(),
            'network': self.get_network_info(),
            'system': self.get_system_info(),
            'timestamp': datetime.now().isoformat()
        }
        
        # Проверяем, что все метрики получены успешно
        if any(value is None for key, value in metrics.items() if key != 'timestamp'):
            logger.warning(f"Не удалось получить все метрики с сервера {self.host}")
            return None
        
        return metrics
    
    def get_server_health(self):
        """
        Оценивает общее состояние сервера на основе метрик.
        
        Returns:
            dict: Оценка состояния сервера или None в случае ошибки.
                'status': Строка ('ok', 'warning', 'critical')
                'cpu_load': Уровень загрузки CPU (%)
                'memory_used': Процент использованной памяти (%)
                'disk_used': Процент использованного дискового пространства (словарь по точкам монтирования)
                'issues': Список обнаруженных проблем
        """
        metrics = self.get_all_metrics()
        if not metrics:
            return None
        
        health = {
            'status': 'ok',
            'cpu_load': 0,
            'memory_used': 0,
            'disk_used': {},
            'issues': []
        }
        
        # Анализ CPU
        if metrics['cpu']:
            health['cpu_load'] = metrics['cpu'].get('total', 0)
            if health['cpu_load'] > 90:
                health['status'] = 'critical'
                health['issues'].append(f"Критическая загрузка CPU: {health['cpu_load']}%")
            elif health['cpu_load'] > 75:
                if health['status'] != 'critical':
                    health['status'] = 'warning'
                health['issues'].append(f"Высокая загрузка CPU: {health['cpu_load']}%")
        
        # Анализ памяти
        if metrics['memory']:
            health['memory_used'] = metrics['memory'].get('percent', 0)
            if health['memory_used'] > 90:
                health['status'] = 'critical'
                health['issues'].append(f"Критическое использование памяти: {health['memory_used']}%")
            elif health['memory_used'] > 80:
                if health['status'] != 'critical':
                    health['status'] = 'warning'
                health['issues'].append(f"Высокое использование памяти: {health['memory_used']}%")
        
        # Анализ дисков
        if metrics['disk']:
            for fs in metrics['disk']:
                mount_point = fs.get('mnt_point', '')
                used_percent = fs.get('percent', 0)
                health['disk_used'][mount_point] = used_percent
                
                if used_percent > 90:
                    health['status'] = 'critical'
                    health['issues'].append(f"Критическое заполнение диска {mount_point}: {used_percent}%")
                elif used_percent > 80:
                    if health['status'] != 'critical':
                        health['status'] = 'warning'
                    health['issues'].append(f"Высокое заполнение диска {mount_point}: {used_percent}%")
        
        return health


def check_server_via_glances(host, port=61208):
    """
    Проверяет доступность сервера через Glances API.
    
    Args:
        host (str): Хост или IP-адрес сервера.
        port (int, optional): Порт Glances API. По умолчанию 61208.
        
    Returns:
        bool: True, если сервер доступен, иначе False.
    """
    glances = GlancesAPI(host, port)
    return glances.is_available()


def get_server_metrics(host, port=61208):
    """
    Получает метрики сервера через Glances API.
    
    Args:
        host (str): Хост или IP-адрес сервера.
        port (int, optional): Порт Glances API. По умолчанию 61208.
        
    Returns:
        dict: Метрики сервера или None в случае ошибки.
    """
    glances = GlancesAPI(host, port)
    return glances.get_all_metrics()


def get_server_health(host, port=61208):
    """
    Получает оценку состояния сервера через Glances API.
    
    Args:
        host (str): Хост или IP-адрес сервера.
        port (int, optional): Порт Glances API. По умолчанию 61208.
        
    Returns:
        dict: Оценка состояния сервера или None в случае ошибки.
    """
    glances = GlancesAPI(host, port)
    return glances.get_server_health()