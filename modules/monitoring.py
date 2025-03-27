"""
Модуль для мониторинга серверов
Включает сбор метрик (CPU, RAM, диск) и проверку доступности
"""

import logging
from datetime import datetime

# MQTT отключен
# from modules.mqtt_manager import MQTTManager
from modules.server_manager import ServerManager
from modules.glances_manager import check_server_via_glances, get_server_metrics, get_server_health
from app import db
from models import Server, ServerMetric, SystemSetting

# Настройка логирования
logger = logging.getLogger(__name__)

class MonitoringManager:
    """
    Менеджер для мониторинга серверов и сбора метрик
    """
    
    @staticmethod
    def check_server_status(server):
        """
        Проверяет статус сервера через Glances API
        
        Args:
            server: объект Server для проверки
            
        Returns:
            bool: True если сервер доступен, False иначе
        """
        try:
            # Сначала пробуем через Glances API как приоритетный метод
            if server.glances_enabled and check_server_via_glances(server.ip_address, server.glances_port or 61208):
                return True
            
            # Если Glances недоступен, пробуем SSH как запасной вариант
            if ServerManager.check_connectivity(server):
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error in server status check: {str(e)}")
            return False
            
    @staticmethod
    def collect_server_metrics(server):
        """
        Собирает метрики сервера (CPU, RAM, Disk) через Glances API или SSH
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            dict: Словарь с метриками или None в случае ошибки
        """
        try:
            # Проверяем настройку MQTT для системы
            mqtt_enabled_setting = SystemSetting.get_value('mqtt_enabled', 'false')
            mqtt_enabled = mqtt_enabled_setting.lower() == 'true' if mqtt_enabled_setting else False
            
            # Сначала пробуем MQTT, если включен
            if mqtt_enabled:
                logger.info(f"Attempting to collect metrics via MQTT for server {server.name}")
                metric = MonitoringManager.collect_server_metrics_mqtt(server)
                if metric:
                    return metric
            
            # Пробуем через Glances API как второй приоритет
            if server.glances_enabled:
                logger.info(f"Attempting to collect metrics via Glances API for server {server.name}")
                metric = MonitoringManager.collect_server_metrics_glances(server)
                if metric:
                    return metric
                else:
                    # Если Glances API не сработал, помечаем сервер как имеющий проблемы с Glances
                    server.glances_error = True
                    db.session.commit()
            
            # Пробуем через SSH как последний вариант
            logger.info(f"Falling back to SSH method for server {server.name}")
            return MonitoringManager.collect_server_metrics_ssh(server)
        except Exception as e:
            logger.error(f"Error in server metrics collection: {str(e)}")
            return None
    
    @staticmethod
    def collect_server_metrics_mqtt(server):
        """
        Собирает метрики сервера через MQTT (отключено)
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            ServerMetric: объект с метриками или None в случае ошибки
        """
        # MQTT отключен - возвращаем None
        return None
    
    @staticmethod
    def collect_server_metrics_glances(server):
        """
        Собирает метрики сервера через Glances API
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            ServerMetric: объект с метриками или None в случае ошибки
        """
        try:
            # Получаем метрики через Glances API
            raw_metrics = get_server_metrics(server.ip_address, server.glances_port or 61208)
            
            if not raw_metrics:
                logger.warning(f"Failed to collect metrics via Glances API for {server.name}, marking Glances as error")
                server.glances_error = True
                db.session.commit()
                return None
            
            # Преобразуем формат метрик
            cpu_percent = raw_metrics.get('cpu', {}).get('total', 0)
            memory_percent = raw_metrics.get('memory', {}).get('percent', 0)
            
            # Для диска берем максимальное заполнение
            disk_percent = 0
            if raw_metrics.get('disk'):
                for fs in raw_metrics['disk']:
                    disk_percent = max(disk_percent, fs.get('percent', 0))
            
            # Получаем load average (берем 1-минутный)
            load_avg = 0
            if raw_metrics.get('system') and 'load' in raw_metrics['system']:
                load_values = raw_metrics['system']['load']
                if isinstance(load_values, list) and len(load_values) > 0:
                    load_avg = load_values[0]
            
            # Создаем объект ServerMetric
            metric = ServerMetric(
                server_id=server.id,
                cpu_usage=cpu_percent,
                memory_usage=memory_percent,
                disk_usage=disk_percent,
                load_average=load_avg,
                timestamp=datetime.now(),
                collection_method='glances'  # Помечаем, что метрики собраны через Glances
            )
            
            # Сохраняем метрики в базе данных
            db.session.add(metric)
            db.session.commit()
            
            # Сбрасываем флаг ошибки Glances, если он был установлен
            if server.glances_error:
                server.glances_error = False
                db.session.commit()
                
            logger.info(f"Collected server metrics via Glances API for {server.name}: CPU {cpu_percent}%, Memory {memory_percent}%, Disk {disk_percent}%")
            
            return metric
        except Exception as e:
            logger.error(f"Error collecting metrics via Glances for {server.name}: {str(e)}")
            server.glances_error = True
            db.session.commit()
            return None
    
    @staticmethod
    def collect_server_metrics_ssh(server):
        """
        Собирает метрики сервера через SSH
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            ServerMetric: объект с метриками или None в случае ошибки
        """
        try:
            # Проверяем соединение с сервером
            if not ServerManager.check_connectivity(server):
                logger.warning(f"Server {server.name} is not reachable via SSH, skipping metrics collection")
                return None
            
            # Получаем метрики через SSH
            cpu_usage = ServerManager.get_cpu_usage(server)
            memory_usage = ServerManager.get_memory_usage(server)
            disk_usage = ServerManager.get_disk_usage(server)
            load_average = ServerManager.get_load_average(server)
            
            # Создаем объект ServerMetric
            metric = ServerMetric(
                server_id=server.id,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                disk_usage=disk_usage,
                load_average=load_average,
                timestamp=datetime.now(),
                collection_method='ssh'  # Помечаем, что метрики собраны через SSH
            )
            
            # Сохраняем метрики в базе данных
            db.session.add(metric)
            db.session.commit()
            
            logger.info(f"Collected server metrics via SSH for {server.name}: CPU {cpu_usage}%, Memory {memory_usage}%, Disk {disk_usage}%")
            
            return metric
        except Exception as e:
            logger.error(f"Error collecting metrics via SSH for {server.name}: {str(e)}")
            return None