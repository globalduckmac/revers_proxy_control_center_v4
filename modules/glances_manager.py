# -*- coding: utf-8 -*-

import json
import logging
import requests
import threading
from datetime import datetime
from modules.telegram_notifier import mask_ip_address

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GlancesManager:
    """
    Класс для работы с Glances API
    """
    
    @staticmethod
    def get_metrics(server_id):
        """
        Получает метрики с сервера через Glances API.
        
        Args:
            server_id: ID сервера в базе данных
            
        Returns:
            dict: Словарь с метриками или None в случае ошибки
        """
        from models import Server
        from app import db
        
        server = Server.query.get(server_id)
        if not server:
            logger.error(f"Сервер с ID {server_id} не найден")
            return None
        
        try:
            # Получаем метрики через Glances API
            url = f"http://{server.ip_address}:{server.glances_port}/api/4/all"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                metrics = response.json()
                
                # Обновляем статус сервера
                server.last_check = datetime.utcnow()
                server.last_status = "online"
                server.glances_available = True
                db.session.commit()
                
                return metrics
            else:
                logger.error(f"Ошибка при получении метрик с сервера {server.name}: HTTP {response.status_code}")
                
                # Обновляем статус сервера
                server.last_check = datetime.utcnow()
                server.last_status = "offline"
                server.glances_available = False
                db.session.commit()
                
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении метрик с сервера {server.name}: {str(e)}")
            
            # Обновляем статус сервера
            server.last_check = datetime.utcnow()
            server.last_status = "offline"
            server.glances_available = False
            db.session.commit()
            
            return None
    
    @staticmethod
    def get_server_metrics_via_api(server):
        """
        Получает метрики с сервера через Glances API и сохраняет их в таблице ServerMetric.
        
        Args:
            server: Объект модели Server
            
        Returns:
            ServerMetric: Созданный объект метрики или None в случае ошибки
        """
        from models import ServerMetric
        from app import app, db
        
        if not server:
            logger.warning("Cannot collect metrics: server is None")
            return None
            
        try:
            # Получаем метрики через Glances API
            url = f"http://{server.ip_address}:{server.glances_port}/api/4/all"
            logger.info(f"Запрос метрик для сервера {server.name} ({server.ip_address})")
            
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                
                # Извлекаем необходимые метрики
                cpu_usage = 0
                memory_usage = 0
                disk_usage = 0
                load_average = "0, 0, 0"
                
                # CPU
                if 'cpu' in data and 'total' in data['cpu']:
                    cpu_usage = data['cpu']['total']
                
                # Memory
                if 'mem' in data and 'percent' in data['mem']:
                    memory_usage = data['mem']['percent']
                
                # Disk
                if 'fs' in data and isinstance(data['fs'], list) and len(data['fs']) > 0:
                    # Находим корневой раздел или используем средний процент
                    if any(disk.get('mnt_point') == '/' for disk in data['fs']):
                        root_disk = next((disk for disk in data['fs'] if disk.get('mnt_point') == '/'), None)
                        if root_disk:
                            disk_usage = root_disk.get('percent', 0)
                    else:
                        total_percent = sum(disk.get('percent', 0) for disk in data['fs'] if 'percent' in disk)
                        disk_count = len([disk for disk in data['fs'] if 'percent' in disk])
                        disk_usage = total_percent / disk_count if disk_count > 0 else 0
                
                # Load Average
                if 'load' in data:
                    load_average = f"{data['load'].get('min1', 0)}, {data['load'].get('min5', 0)}, {data['load'].get('min15', 0)}"
                
                # Используем контекст приложения для работы с БД в отдельном потоке
                with app.app_context():
                    # Создаем новую запись метрики
                    metric = ServerMetric(
                        server_id=server.id,
                        cpu_usage=cpu_usage,
                        memory_usage=memory_usage,
                        disk_usage=disk_usage,
                        load_average=load_average,
                    )
                    
                    # Сохраняем метрику в БД
                    db.session.add(metric)
                    db.session.commit()
                    
                    logger.info(f"Сохранена метрика для сервера {server.name}: CPU {cpu_usage}%, Memory {memory_usage}%, Disk {disk_usage}%")
                    return metric
            else:
                logger.warning(f"Ошибка запроса метрик для сервера {server.name}: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка получения метрик для сервера {server.name}: {str(e)}")
            return None
    
    @staticmethod
    def check_external_server_glances(ip_address, port=61208, timeout=5):
        """
        Проверяет доступность Glances API на внешнем сервере.
        
        Args:
            ip_address: IP-адрес сервера
            port: Порт Glances API (по умолчанию 61208)
            timeout: Таймаут соединения в секундах
            
        Returns:
            bool: True если Glances доступен, False если нет
        """
        try:
            logger.debug(f"Проверка соединения с Glances API на внешнем сервере {ip_address}")
            url = f"http://{ip_address}:{port}/api/4/cpu"
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                logger.debug(f"Соединение с Glances API на внешнем сервере {ip_address} успешно установлено")
                return True
            else:
                logger.error(f"Ошибка соединения с Glances API на внешнем сервере {ip_address}: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Ошибка соединения с Glances API на внешнем сервере {ip_address}: {str(e)}")
            return False

    @staticmethod
    def update_external_server_metrics(external_server):
        """
        Обновляет метрики внешнего сервера, используя Glances API.
        
        Args:
            external_server: Объект модели ExternalServer
            
        Returns:
            dict: Словарь с полученными метриками или None в случае ошибки
        """
        from app import db
        from models import ExternalServerMetric
        import json
        
        logger.debug(f"Получение метрик с внешнего сервера {external_server.name}")
        try:
            # Получаем метрики CPU
            cpu_url = f"http://{external_server.ip_address}:{external_server.glances_port}/api/4/cpu"
            cpu_response = requests.get(cpu_url, timeout=5)
            if cpu_response.status_code == 200:
                cpu_data = cpu_response.json()
                # Сохраняем общую загрузку CPU
                cpu_metric = ExternalServerMetric(
                    external_server_id=external_server.id,
                    metric_type='cpu',
                    metric_name='total',
                    metric_value=str(cpu_data.get('total', 0))
                )
                db.session.add(cpu_metric)
                
                # Сохраняем детальную информацию о CPU
                cpu_detail_metric = ExternalServerMetric(
                    external_server_id=external_server.id,
                    metric_type='cpu',
                    metric_name='detail',
                    metric_value=json.dumps(cpu_data)
                )
                db.session.add(cpu_detail_metric)
            
            # Получаем метрики памяти
            mem_url = f"http://{external_server.ip_address}:{external_server.glances_port}/api/4/mem"
            mem_response = requests.get(mem_url, timeout=5)
            if mem_response.status_code == 200:
                mem_data = mem_response.json()
                # Сохраняем процент использования памяти
                mem_metric = ExternalServerMetric(
                    external_server_id=external_server.id,
                    metric_type='memory',
                    metric_name='percent',
                    metric_value=str(mem_data.get('percent', 0))
                )
                db.session.add(mem_metric)
                
                # Сохраняем детальную информацию о памяти
                mem_detail_metric = ExternalServerMetric(
                    external_server_id=external_server.id,
                    metric_type='memory',
                    metric_name='detail',
                    metric_value=json.dumps(mem_data)
                )
                db.session.add(mem_detail_metric)
            
            # Получаем метрики дисков
            disk_url = f"http://{external_server.ip_address}:{external_server.glances_port}/api/4/fs"
            disk_response = requests.get(disk_url, timeout=5)
            if disk_response.status_code == 200:
                disk_data = disk_response.json()
                # Сохраняем детальную информацию о дисках
                disk_detail_metric = ExternalServerMetric(
                    external_server_id=external_server.id,
                    metric_type='disk',
                    metric_name='detail',
                    metric_value=json.dumps(disk_data)
                )
                db.session.add(disk_detail_metric)
            
            # Получаем метрики сети
            net_url = f"http://{external_server.ip_address}:{external_server.glances_port}/api/4/network"
            net_response = requests.get(net_url, timeout=5)
            if net_response.status_code == 200:
                net_data = net_response.json()
                # Сохраняем детальную информацию о сети
                net_detail_metric = ExternalServerMetric(
                    external_server_id=external_server.id,
                    metric_type='network',
                    metric_name='detail',
                    metric_value=json.dumps(net_data)
                )
                db.session.add(net_detail_metric)
            
            # Сохраняем все метрики в базу данных
            db.session.commit()
            logger.info(f"Метрики внешнего сервера {external_server.name} успешно обновлены")
            return True
        except Exception as e:
            logger.error(f"Ошибка при получении метрик с внешнего сервера {external_server.name}: {str(e)}")
            return False

    @staticmethod
    def get_detailed_metrics(server_id):
        """
        Получает детальные метрики с сервера через Glances API.
        
        Args:
            server_id: ID сервера в базе данных
            
        Returns:
            dict: Словарь с детальными метриками или ошибкой
        """
        from models import Server
        
        server = Server.query.get(server_id)
        if not server:
            return {
                'success': False, 
                'message': f'Сервер с ID {server_id} не найден'
            }
        
        try:
            # Получаем метрики через Glances API
            url = f"http://{server.ip_address}:{server.glances_port}/api/4/all"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                # Удалось получить метрики
                data = response.json()
                
                # Подготавливаем все необходимые данные с проверками на отсутствие
                # Создаем безопасные данные для всех ожидаемых полей
                
                # Базовая структура для всех метрик с пустыми значениями по умолчанию
                metrics = {
                    'success': True,
                    'cpu': {
                        'total': 0,
                        'user': 0,
                        'system': 0,
                        'idle': 100
                    },
                    'mem': {
                        'percent': 0,
                        'total': 0,
                        'used': 0,
                        'free': 0
                    },
                    'memswap': {  # Добавляем memswap, который используется в шаблоне
                        'percent': 0,
                        'total': 0,
                        'used': 0,
                        'free': 0
                    },
                    'disk': [],
                    'fs': [],  # Для обратной совместимости
                    'network': {},
                    'load': {
                        'min1': 0,
                        'min5': 0,
                        'min15': 0
                    },
                    'uptime': 0,
                    'processes': [],
                    'raw_data': data  # Полные данные для отладки
                }
                
                # Заполняем данными из API если они есть
                if 'cpu' in data:
                    metrics['cpu'] = data['cpu']
                
                if 'mem' in data:
                    metrics['mem'] = data['mem']
                
                if 'memswap' in data:
                    metrics['memswap'] = data['memswap']
                
                if 'fs' in data:
                    metrics['disk'] = data['fs']
                    metrics['fs'] = data['fs']  # Для обратной совместимости
                
                if 'network' in data:
                    # Обработка сетевых данных (они могут быть в формате словаря или списка в зависимости от версии Glances)
                    if 'network' in data:
                        network_dict = {}
                        if isinstance(data['network'], dict):
                            # Стандартный формат: словарь с интерфейсами
                            metrics['network'] = data['network']
                        else:
                            # Формат списка (встречается в некоторых версиях Glances)
                            # Преобразуем список интерфейсов в словарь для совместимости
                            try:
                                for item in data['network']:
                                    if isinstance(item, dict) and 'interface_name' in item:
                                        network_dict[item['interface_name']] = item
                                metrics['network'] = network_dict
                            except Exception as e:
                                logger.error(f"Error converting network data: {str(e)}")
                                metrics['network'] = {}
                
                if 'load' in data:
                    metrics['load'] = data['load']
                
                if 'uptime' in data:
                    metrics['uptime'] = data['uptime']
                
                if 'processlist' in data:
                    metrics['processes'] = data['processlist'][:10]  # Только первые 10 процессов
                
                # Возвращаем подготовленные данные с гарантированной структурой
                return metrics
            else:
                # API недоступен
                return {
                    'success': False,
                    'message': f'Glances API вернул код {response.status_code}'
                }
                
        except requests.exceptions.ConnectionError:
            # Нет соединения
            return {
                'success': False,
                'message': 'Невозможно установить соединение с Glances API'
            }
        except requests.exceptions.Timeout:
            # Тайм-аут соединения
            return {
                'success': False,
                'message': 'Тайм-аут соединения с Glances API'
            }
        except Exception as e:
            # Другие ошибки
            return {
                'success': False,
                'message': f'Ошибка при получении метрик: {str(e)}'
            }
    
    @staticmethod
    def check_glances_status(server_id):
        """
        Проверяет статус Glances на указанном сервере.
        Приоритизирует проверку API напрямую без SSH.
        
        Args:
            server_id: ID сервера в базе данных
            
        Returns:
            dict: Словарь со статусом и дополнительной информацией
        """
        from models import Server, ServerLog
        from app import db
        from modules.server_manager import ServerManager
        import requests
        from datetime import datetime
        
        server = Server.query.get(server_id)
        if not server:
            return {
                'success': False, 
                'message': f'Сервер с ID {server_id} не найден',
                'running': False,
                'api_accessible': False
            }
        
        # Пробуем проверить API без SSH (основной способ)
        try:
            # Проверяем доступность Glances API на стандартном порту
            url = f"http://{server.ip_address}:61208/api/4/all"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                # API доступен напрямую, обновляем информацию сервера
                server.glances_port = 61208
                server.glances_status = "active"
                server.glances_available = True
                server.glances_installed = True
                server.status = 'active'  # Обновляем общий статус сервера
                server.last_glances_check = datetime.utcnow()
                
                # Создаем запись в журнале
                log = ServerLog(
                    server_id=server.id,
                    action="check_glances",
                    status="info",
                    message=f"Glances API доступен напрямую"
                )
                db.session.add(log)
                db.session.commit()
                
                return {
                    'success': True,
                    'message': 'Glances API доступен',
                    'running': True,
                    'api_accessible': True
                }
        except Exception as e:
            logger.warning(f"Glances API недоступен напрямую для сервера {server.name}: {str(e)}")
            
            # Если API недоступен, обновляем статус сервера
            server.glances_status = "error"
            server.glances_available = False
            server.last_glances_check = datetime.utcnow()
            
            # Создаем запись в журнале об ошибке
            log = ServerLog(
                server_id=server.id,
                action="check_glances",
                status="error",
                message=f"Ошибка при доступе к Glances API напрямую: {str(e)}"
            )
            db.session.add(log)
            db.session.commit()
            
            # Пытаемся проверить SSH только если это настроено в конфигурации сервера
            ssh_check_enabled = getattr(server, 'ssh_check_enabled', False)
            
            if not ssh_check_enabled:
                return {
                    'success': False,
                    'message': f'Glances API недоступен, а проверка через SSH отключена',
                    'running': False,
                    'api_accessible': False
                }
            
            # Проверка через SSH (альтернативный способ, если включен)
            if not ServerManager.check_connectivity(server):
                return {
                    'success': False,
                    'message': 'Glances API недоступен, а SSH-соединение не работает',
                    'running': False,
                    'api_accessible': False
                }
                
            try:
                # Подключаемся к серверу по SSH
                ssh_client = ServerManager.get_ssh_client(server)
                
                # Проверяем запущен ли сервис Glances через systemd
                check_cmd = "systemctl is-active glances.service"
                stdin, stdout, stderr = ssh_client.exec_command(check_cmd)
                output = stdout.read().decode('utf-8').strip()
                
                service_running = (output == "active")
                
                # Проверяем доступность API из консоли
                api_cmd = "curl -s --connect-timeout 3 http://localhost:61208/api/4/all 2>/dev/null | grep -q cpu && echo 'accessible' || echo 'not accessible'"
                stdin, stdout, stderr = ssh_client.exec_command(api_cmd)
                api_output = stdout.read().decode('utf-8').strip()
                
                api_accessible = (api_output == "accessible")
                
                # Обновляем информацию о сервере
                server.glances_port = 61208
                
                if service_running and api_accessible:
                    server.glances_status = "active"
                    server.glances_available = True
                    server.glances_installed = True
                elif service_running:
                    server.glances_status = "service_running"
                    server.glances_available = False
                    server.glances_installed = True
                else:
                    server.glances_status = "error"
                    server.glances_available = False
                    
                server.last_glances_check = datetime.utcnow()
                db.session.commit()
                
                # Создаем запись в журнале
                log = ServerLog(
                    server_id=server.id,
                    action="check_glances",
                    status="info",
                    message=f"Статус Glances через SSH: сервис {'запущен' if service_running else 'не запущен'}, API {'доступен' if api_accessible else 'недоступен'}"
                )
                db.session.add(log)
                db.session.commit()
                
                return {
                    'success': True,
                    'message': f"Glances: сервис {'запущен' if service_running else 'не запущен'}, API {'доступен' if api_accessible else 'недоступен'}",
                    'running': service_running,
                    'api_accessible': api_accessible
                }
                    
            except Exception as e:
                logger.error(f"Ошибка при проверке статуса Glances через SSH: {str(e)}")
                
                # Создаем запись в журнале об ошибке
                log = ServerLog(
                    server_id=server.id,
                    action="check_glances",
                    status="error",
                    message=f"Ошибка при проверке статуса Glances через SSH: {str(e)}"
                )
                db.session.add(log)
                db.session.commit()
                
                return {
                    'success': False,
                    'message': f'Ошибка при проверке статуса Glances через SSH: {str(e)}',
                    'running': False,
                    'api_accessible': False
                }
        
        # Если API доступен напрямую, и мы дошли сюда, то возвращаем успешный результат
        return {
            'success': True,
            'message': 'Glances API доступен',
            'running': True,
            'api_accessible': True
        }
    
    @staticmethod
    def check_glances(server):
        """
        Проверяет доступность Glances API на указанном сервере и собирает метрики.
        Также сохраняет метрики в таблице ServerMetric для отображения истории.
        
        Args:
            server: Объект сервера (Server) для проверки
            
        Returns:
            bool: True если соединение успешно, False в противном случае
        """
        logger.info(f"Проверка Glances API на сервере {server.name} ({server.ip_address})")
        
        try:
            # Проверяем, включен ли Glances на сервере
            if not server.glances_enabled:
                logger.warning(f"Glances не включен на сервере {server.name}, пропускаем")
                return False
                
            # Проверяем доступность Glances
            from app import db
            from datetime import datetime
            import json
            import requests
            
            # Используем стандартный порт 61208
            glances_url = f"http://{server.ip_address}:61208/api/4/all"
            response = requests.get(glances_url, timeout=5)
            
            if response.status_code == 200:
                # Соединение успешно установлено
                server.last_glances_check = datetime.utcnow()
                server.glances_status = "active"
                server.glances_available = True
                server.glances_port = 61208
                server.glances_installed = True
                
                # Сохраняем некоторые метрики
                data = response.json()
                
                # CPU
                cpu_value = 0
                if 'cpu' in data:
                    cpu_value = data['cpu']['total']
                    server.glances_cpu = cpu_value
                    logger.debug(f"CPU загрузка: {server.glances_cpu}%")
                
                # Memory
                mem_value = 0
                if 'mem' in data:
                    mem_value = data['mem']['percent']
                    server.glances_memory = mem_value
                    logger.debug(f"Memory загрузка: {server.glances_memory}%")
                
                # Disk
                disk_value = 0
                if 'fs' in data and len(data['fs']) > 0:
                    disks_info = []
                    for disk in data['fs']:
                        disks_info.append({
                            'device': disk['device_name'],
                            'mountpoint': disk['mnt_point'],
                            'percent': disk['percent']
                        })
                        
                        # Для расчета средней нагрузки диска
                        if 'percent' in disk:
                            disk_value += disk['percent']
                            
                    # Средняя нагрузка дисков
                    if len(disks_info) > 0:
                        disk_value = disk_value / len(disks_info)
                    server.glances_disk = json.dumps(disks_info)
                    logger.debug(f"Диски: {len(disks_info)} разделов")
                
                # Network
                if 'network' in data:
                    networks_info = []
                    # Проверяем формат данных сети (словарь или список)
                    if isinstance(data['network'], dict):
                        # Обычный формат - словарь интерфейсов
                        for name, netif in data['network'].items():
                            if name not in ['lo', 'total']:
                                networks_info.append({
                                    'interface': name,
                                    'rx': netif.get('rx', 0),
                                    'tx': netif.get('tx', 0)
                                })
                    else:
                        # Альтернативный формат - список интерфейсов
                        # Нормальный случай, некоторые версии Glances используют список вместо словаря
                        try:
                            for item in data['network']:
                                if isinstance(item, dict):
                                    interface_name = item.get('interface_name', 'unknown')
                                    if interface_name not in ['lo', 'total']:
                                        networks_info.append({
                                            'interface': interface_name,
                                            'rx': item.get('rx', 0),
                                            'tx': item.get('tx', 0)
                                        })
                        except Exception as e:
                            logger.error(f"Error processing network list data: {str(e)}")
                    
                    server.glances_network = json.dumps(networks_info)
                    logger.debug(f"Сеть: {len(networks_info)} интерфейсов")
                
                # Load average
                if 'load' in data:
                    server.glances_load = f"{data['load']['min1']}, {data['load']['min5']}, {data['load']['min15']}"
                    logger.debug(f"Load average: {server.glances_load}")
                
                # Uptime
                if 'uptime' in data:
                    # Проверяем формат uptime - может прийти как число или как строка
                    uptime_value = data['uptime']
                    if isinstance(uptime_value, str):
                        # Если строка в формате "ЧЧ:ММ:СС", конвертируем в секунды
                        try:
                            if ":" in uptime_value:
                                parts = uptime_value.split(":")
                                if len(parts) == 3:  # формат "ЧЧ:ММ:СС"
                                    hours, minutes, seconds = parts
                                    total_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
                                    server.glances_uptime = total_seconds
                                elif len(parts) == 2:  # формат "ММ:СС"
                                    minutes, seconds = parts
                                    total_seconds = int(minutes) * 60 + int(seconds)
                                    server.glances_uptime = total_seconds
                                else:
                                    # Если формат неизвестен, сохраняем 0
                                    logger.warning(f"Неизвестный формат uptime: {uptime_value}, устанавливаем 0")
                                    server.glances_uptime = 0
                            else:
                                # Пробуем преобразовать строку в число
                                server.glances_uptime = int(float(uptime_value))
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Ошибка преобразования uptime '{uptime_value}': {str(e)}, устанавливаем 0")
                            server.glances_uptime = 0
                    else:
                        # Если это число, сохраняем как есть
                        try:
                            server.glances_uptime = int(uptime_value)
                        except (ValueError, TypeError):
                            logger.warning(f"Не удалось преобразовать uptime {uptime_value} в целое число, устанавливаем 0")
                            server.glances_uptime = 0
                    
                    logger.debug(f"Uptime: {server.glances_uptime} секунд")
                
                # Сохраняем изменения
                db.session.commit()
                
                # Сохраняем метрики в таблице ServerMetric для истории сразу, без отдельного потока
                try:
                    # Вызываем метод напрямую в текущем потоке, 
                    # так как мы уже в контексте Flask приложения
                    metric = GlancesManager.get_server_metrics_via_api(server)
                    if metric:
                        logger.debug(f"Метрики успешно сохранены для сервера {server.name}")
                    else:
                        logger.warning(f"Не удалось сохранить метрики для сервера {server.name}")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении метрик: {str(e)}")
                
                logger.info(f"Glances метрики для сервера {server.name} успешно обновлены")
                return True
            else:
                logger.warning(f"Не удалось получить данные от Glances API. Статус: {response.status_code}")
                server.glances_status = "error"
                server.glances_available = False
                server.last_glances_check = datetime.utcnow()
                db.session.commit()
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при получении метрик с сервера {server.name}: {str(e)}")
            # Обновляем статус
            from app import db
            from datetime import datetime
            server.glances_status = "error"
            server.glances_available = False
            server.last_glances_check = datetime.utcnow()
            db.session.commit()
            return False
            
    @staticmethod
    def install_glances(server_id):
        """
        Устанавливает Glances на указанном сервере.
        
        Args:
            server_id: ID сервера в базе данных
            
        Returns:
            dict: Словарь с результатом установки и дополнительной информацией
        """
        from models import Server, ServerLog
        from app import db
        import os
        import tempfile
        from subprocess import Popen, PIPE
        import threading
        
        # Получаем информацию о сервере
        server = Server.query.get(server_id)
        if not server:
            return {
                'success': False,
                'message': f'Сервер с ID {server_id} не найден'
            }
        
        # Проверяем, что у нас есть доступ к серверу
        from modules.server_manager import ServerManager
        if not ServerManager.check_connectivity(server):
            return {
                'success': False,
                'message': 'Нет доступа к серверу. Проверьте SSH-соединение.'
            }
            
        # Создаем запись в журнале о начале установки
        log = ServerLog(
            server_id=server.id,
            action="install_glances",
            status="start",
            message=f"Начало установки Glances на сервере {server.name}"
        )
        db.session.add(log)
        db.session.commit()
                
        # Функция для выполнения установки в отдельном потоке
        def install_process(server_id):
            from app import app
            from models import Server
            
            # Создаем контекст приложения для работы с БД в отдельном потоке
            with app.app_context():
                try:
                    # Получаем информацию о сервере
                    server = Server.query.get(server_id)
                    if not server:
                        logger.error(f"Сервер с ID {server_id} не найден")
                        return
                    
                    # Использование параметров SSH в коде
                    ssh_client = ServerManager.get_ssh_client(server)
                    
                    # Генерируем временный скрипт установки
                    install_commands = [
                        "#!/bin/bash",
                        "echo 'Установка Glances на сервер...'",
                        
                        "# 1. Обновление репозиториев",
                        "echo '1. Обновление репозиториев...'",
                        "sudo apt update",
                        
                        "# 2. Установка Python и pip",
                        "echo '2. Установка Python и pip...'",
                        "sudo apt install -y python3-pip",
                        
                        "# 3. Установка Glances через pip",
                        "echo '3. Установка Glances...'",
                        "sudo pip3 install --upgrade glances",
                        
                        "# 4. Установка необходимых зависимостей для веб-интерфейса",
                        "echo '4. Установка зависимостей для веб-интерфейса...'",
                        "sudo pip3 install fastapi uvicorn jinja2",
                        
                        "# 5-6. Создание файла службы systemd",
                        "echo '5. Создание файла службы systemd...'",
                        "cat > /tmp/glances.service << EOF",
                        "[Unit]",
                        "Description=Glances monitoring tool (web mode)",
                        "After=network.target",
                        "",
                        "[Service]",
                        "ExecStart=/usr/local/bin/glances -w",
                        "Restart=always",
                        "",
                        "[Install]",
                        "WantedBy=multi-user.target",
                        "EOF",
                        
                        "sudo mv /tmp/glances.service /etc/systemd/system/glances.service",
                        
                        "# 7. Перезагрузка systemd после создания нового файла службы",
                        "echo '7. Перезагрузка systemd...'",
                        "sudo systemctl daemon-reload",
                        
                        "# 8. Включение автозапуска Glances",
                        "echo '8. Включение автозапуска Glances...'",
                        "sudo systemctl enable glances.service",
                        
                        "# 9. Запуск службы Glances",
                        "echo '9. Запуск службы Glances...'",
                        "sudo systemctl start glances.service",
                        
                        "# Проверка статуса службы",
                        "echo 'Проверка статуса службы Glances...'",
                        "sudo systemctl status glances.service",
                        
                        "echo 'Установка Glances завершена!'"
                    ]
                    
                    install_script = "\n".join(install_commands)
                    
                    # Выполняем команды через SSH
                    logger.info(f"Запуск установки Glances на сервере {server.name} ({server.ip_address})")
                    
                    stdin, stdout, stderr = ssh_client.exec_command("mktemp")
                    remote_temp_file = stdout.read().decode('utf-8').strip()
                    
                    # Записываем скрипт на удаленный сервер
                    stdin, stdout, stderr = ssh_client.exec_command(f"cat > {remote_temp_file}")
                    stdin.write(install_script)
                    stdin.flush()
                    stdin.channel.shutdown_write()
                    
                    # Делаем скрипт исполняемым и запускаем
                    ssh_client.exec_command(f"chmod +x {remote_temp_file}")
                    stdin, stdout, stderr = ssh_client.exec_command(f"bash {remote_temp_file}")
                    
                    # Ожидаем завершения и получаем вывод
                    exit_code = stdout.channel.recv_exit_status()
                    output = stdout.read().decode('utf-8')
                    error_output = stderr.read().decode('utf-8')
                    
                    # Удаляем временный файл
                    ssh_client.exec_command(f"rm -f {remote_temp_file}")
                    
                    # Анализируем результат
                    if exit_code == 0:
                        logger.info(f"Установка Glances на сервере {server.name} успешно завершена")
                        
                        # Обновляем статус сервера
                        server = Server.query.get(server.id)  # Перезагружаем сервер из БД
                        server.glances_enabled = True
                        server.glances_status = "installed"
                        server.glances_port = 61208  # Устанавливаем стандартный порт API
                        server.glances_installed = True
                        db.session.commit()
                        
                        # Создаем запись в журнале
                        log = ServerLog(
                            server_id=server.id,
                            action="install_glances",
                            status="success",
                            message=f"Glances успешно установлен на сервере {server.name}"
                        )
                        db.session.add(log)
                        db.session.commit()
                        
                    else:
                        logger.error(f"Ошибка при установке Glances на сервере {server.name}: {error_output}")
                        
                        # Создаем запись в журнале об ошибке
                        log = ServerLog(
                            server_id=server.id,
                            action="install_glances",
                            status="error",
                            message=f"Ошибка при установке Glances: {error_output[:200]}"
                        )
                        db.session.add(log)
                        db.session.commit()
                        
                except Exception as e:
                    logger.error(f"Ошибка при установке Glances: {str(e)}")
                    
                    try:
                        # Получаем актуальный объект сервера
                        current_server = Server.query.get(server_id)
                        
                        # Создаем запись в журнале об ошибке
                        if current_server:
                            server_id_for_log = current_server.id
                        else:
                            server_id_for_log = None
                            
                        log = ServerLog(
                            server_id=server_id_for_log,
                            action="install_glances",
                            status="error",
                            message=f"Исключение при установке Glances: {str(e)}"
                        )
                        db.session.add(log)
                        db.session.commit()
                    except Exception as log_error:
                        logger.error(f"Ошибка при создании лога: {str(log_error)}")
        
        # Запускаем асинхронный процесс установки
        thread = threading.Thread(target=install_process, args=(server.id,))
        thread.daemon = True
        thread.start()
        
        return {
            'success': True,
            'message': 'Установка Glances запущена в фоновом режиме. Процесс может занять несколько минут.'
        }
    
    @staticmethod
    def restart_glances_service(server_id):
        """
        Перезапускает сервис Glances на указанном сервере.
        
        Args:
            server_id: ID сервера в базе данных
            
        Returns:
            dict: Словарь с результатом перезапуска и дополнительной информацией
        """
        from models import Server, ServerLog
        from app import db
        
        # Получаем информацию о сервере
        server = Server.query.get(server_id)
        if not server:
            return {
                'success': False,
                'message': f'Сервер с ID {server_id} не найден'
            }
        
        # Проверяем, что у нас есть доступ к серверу
        from modules.server_manager import ServerManager
        if not ServerManager.check_connectivity(server):
            return {
                'success': False,
                'message': 'Нет доступа к серверу. Проверьте SSH-соединение.'
            }
            
        try:
            # Подключаемся к серверу по SSH
            ssh_client = ServerManager.get_ssh_client(server)
            
            # Перезапускаем сервис Glances через systemd
            cmd = "sudo systemctl restart glances.service"
            
            stdin, stdout, stderr = ssh_client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            
            if exit_code == 0:
                # Создаем запись в журнале об успешном перезапуске
                log = ServerLog(
                    server_id=server.id,
                    action="restart_glances",
                    status="success",
                    message=f"Сервис Glances успешно перезапущен на сервере {server.name}"
                )
                db.session.add(log)
                db.session.commit()
                
                return {
                    'success': True,
                    'message': 'Сервис Glances успешно перезапущен'
                }
            else:
                error_message = stderr.read().decode('utf-8')
                
                # Создаем запись в журнале об ошибке
                log = ServerLog(
                    server_id=server.id,
                    action="restart_glances",
                    status="error",
                    message=f"Ошибка при перезапуске Glances: {error_message[:200]}"
                )
                db.session.add(log)
                db.session.commit()
                
                return {
                    'success': False,
                    'message': f'Ошибка при перезапуске сервиса: {error_message}'
                }
                
        except Exception as e:
            logger.error(f"Ошибка при перезапуске Glances: {str(e)}")
            
            # Создаем запись в журнале об ошибке
            log = ServerLog(
                server_id=server.id,
                action="restart_glances",
                status="error",
                message=f"Исключение при перезапуске Glances: {str(e)}"
            )
            db.session.add(log)
            db.session.commit()
            
            return {
                'success': False,
                'message': f'Ошибка: {str(e)}'
            }
            
    @staticmethod
    def collect_server_metrics(server_id):
        """
        Собирает метрики с указанного сервера.
        
        Args:
            server_id: ID сервера в базе данных
            
        Returns:
            dict: Словарь с собранными метриками и статусом выполнения
        """
        from models import Server
        from app import db
        
        server = Server.query.get(server_id)
        if not server:
            return {
                'success': False,
                'message': f'Сервер с ID {server_id} не найден'
            }
            
        # Проверяем Glances на сервере и собираем метрики
        if GlancesManager.check_glances(server):
            return {
                'success': True,
                'message': 'Метрики успешно собраны',
                'cpu_usage': server.glances_cpu,
                'memory_usage': server.glances_memory,
                'disk_usage': server.glances_disk,
                'last_check': server.last_glances_check.strftime('%Y-%m-%d %H:%M:%S') if server.last_glances_check else 'Н/Д'
            }
        else:
            return {
                'success': False,
                'message': 'Не удалось собрать метрики с сервера'
            }
    
    @staticmethod
    def diagnose_glances_installation(server_id):
        """
        Выполняет расширенную диагностику установки Glances на сервере.
        
        Args:
            server_id: ID сервера в базе данных
            
        Returns:
            dict: Словарь с результатами диагностики
        """
        from models import Server
        from modules.server_manager import ServerManager
        
        # Получаем информацию о сервере
        server = Server.query.get(server_id)
        if not server:
            return {
                'success': False,
                'message': f'Сервер с ID {server_id} не найден'
            }
        
        # Проверяем, что у нас есть доступ к серверу
        if not ServerManager.check_connectivity(server):
            return {
                'success': False,
                'message': 'Нет доступа к серверу. Проверьте SSH-соединение.'
            }
            
        results = {
            'success': True,
            'server_name': server.name,
            'server_ip': server.ip_address,
            'glances_enabled': server.glances_enabled,
            'glances_port': server.glances_port,
            'glances_status': server.glances_status,
            'tests': []
        }
        
        try:
            # Подключаемся к серверу по SSH
            ssh_client = ServerManager.get_ssh_client(server)
            
            # Тест 1: Проверка установлен ли Glances
            stdin, stdout, stderr = ssh_client.exec_command("which glances")
            glances_path = stdout.read().decode('utf-8').strip()
            
            if glances_path:
                results['tests'].append({
                    'name': 'Проверка установки Glances',
                    'status': 'success',
                    'message': f'Glances установлен: {glances_path}'
                })
                
                # Тест 2: Проверка версии Glances
                stdin, stdout, stderr = ssh_client.exec_command("glances --version")
                glances_version = stdout.read().decode('utf-8').strip()
                
                results['tests'].append({
                    'name': 'Версия Glances',
                    'status': 'info',
                    'message': glances_version
                })
                
                # Тест 3: Проверка запущен ли сервис Glances
                stdin, stdout, stderr = ssh_client.exec_command(
                    "systemctl is-active glances 2>/dev/null || "
                    "supervisorctl status glances 2>/dev/null || "
                    "ps aux | grep -v grep | grep 'glances -w' | wc -l"
                )
                service_status = stdout.read().decode('utf-8').strip()
                
                if service_status and service_status != "0":
                    results['tests'].append({
                        'name': 'Статус сервиса Glances',
                        'status': 'success',
                        'message': 'Сервис Glances запущен'
                    })
                else:
                    results['tests'].append({
                        'name': 'Статус сервиса Glances',
                        'status': 'error',
                        'message': 'Сервис Glances не запущен'
                    })
                
                # Тест 4: Проверка доступности порта
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"nc -z -w1 localhost {server.glances_port} && echo 'Port open' || echo 'Port closed'"
                )
                port_status = stdout.read().decode('utf-8').strip()
                
                if "Port open" in port_status:
                    results['tests'].append({
                        'name': f'Доступность порта {server.glances_port}',
                        'status': 'success',
                        'message': 'Порт открыт и доступен'
                    })
                else:
                    results['tests'].append({
                        'name': f'Доступность порта {server.glances_port}',
                        'status': 'error',
                        'message': 'Порт закрыт или недоступен'
                    })
                
                # Тест 5: Проверка доступности API через curl
                stdin, stdout, stderr = ssh_client.exec_command(
                    f"curl -s http://localhost:{server.glances_port}/api/4/cpu | grep -q 'total' && echo 'API available' || echo 'API unavailable'"
                )
                api_status = stdout.read().decode('utf-8').strip()
                
                if "API available" in api_status:
                    results['tests'].append({
                        'name': 'Доступность Glances API',
                        'status': 'success',
                        'message': 'API доступен через localhost'
                    })
                else:
                    results['tests'].append({
                        'name': 'Доступность Glances API',
                        'status': 'error',
                        'message': 'API недоступен через localhost'
                    })
                
            else:
                results['tests'].append({
                    'name': 'Проверка установки Glances',
                    'status': 'error',
                    'message': 'Glances не установлен на сервере'
                })
            
            # Тест 6: Проверка внешней доступности API
            import requests
            try:
                api_url = f"http://{server.ip_address}:{server.glances_port}/api/4/cpu"
                response = requests.get(api_url, timeout=5)
                
                if response.status_code == 200 and 'total' in response.json():
                    results['tests'].append({
                        'name': 'Внешняя доступность API',
                        'status': 'success',
                        'message': 'API доступен извне'
                    })
                else:
                    results['tests'].append({
                        'name': 'Внешняя доступность API',
                        'status': 'error',
                        'message': f'API недоступен извне. Код: {response.status_code}'
                    })
            except Exception as e:
                results['tests'].append({
                    'name': 'Внешняя доступность API',
                    'status': 'error',
                    'message': f'Ошибка при проверке API: {str(e)}'
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при диагностике Glances: {str(e)}")
            
            results['success'] = False
            results['message'] = f'Ошибка при выполнении диагностики: {str(e)}'
            
            return results
    
    @staticmethod
    def check_all_external_servers():
        """
        Проверяет доступность всех активных внешних серверов и обновляет их метрики.
        
        Returns:
            dict: Статистика проверки серверов
        """
        from models import ExternalServer, ServerLog
        from app import db
        from datetime import datetime
        from modules.telegram_notifier import mask_ip_address
        
        results = {"total": 0, "online": 0, "offline": 0}
        
        # Получаем все активные внешние серверы
        external_servers = ExternalServer.query.filter_by(is_active=True).all()
        results["total"] = len(external_servers)
        
        for server in external_servers:
            # Маскируем IP-адрес для логирования
            masked_ip = mask_ip_address(server.ip_address)
            logger.info(f"Проверка внешнего сервера {server.name} ({masked_ip})")
            try:
                # Проверяем доступность Glances
                status = GlancesManager.check_external_server_glances(
                    server.ip_address, 
                    server.glances_port
                )
                
                # Сохраняем предыдущий статус перед обновлением
                previous_status = server.last_status
                
                if status:
                    results["online"] += 1
                    
                    # Проверяем изменение статуса (был offline, стал online)
                    status_changed = previous_status == "offline"
                    
                    server.last_status = "online"
                    server.last_check = datetime.utcnow()
                    
                    # Обновляем метрики сервера
                    GlancesManager.update_external_server_metrics(server)
                    
                    # Если статус изменился, отправляем уведомление о восстановлении
                    if status_changed:
                        # Маскируем IP-адрес для записи в журнал
                        masked_ip = mask_ip_address(server.ip_address)
                        log = ServerLog(
                            server_id=None,
                            action="external_server_recovered",
                            status="success",
                            message=f"Внешний сервер {server.name} ({masked_ip}) снова доступен"
                        )
                        db.session.add(log)
                        
                        # Отправляем уведомление в Telegram
                        from modules.telegram_notifier import TelegramNotifier
                        
                        TelegramNotifier.send_success(
                            f"✅ Внешний сервер {server.name} ({masked_ip}) снова доступен\n"
                            f"Время проверки: {datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S')}"
                        )
                        
                        logger.info(f"Статус внешнего сервера {server.name} изменился: offline -> online")
                    else:
                        logger.info(f"Внешний сервер {server.name} доступен, метрики обновлены")
                else:
                    results["offline"] += 1
                    
                    # Проверяем изменение статуса (был online, стал offline)
                    status_changed = previous_status == "online" or previous_status is None
                    
                    server.last_status = "offline"
                    server.last_check = datetime.utcnow()
                    
                    # Создаем запись в журнале
                    masked_ip = mask_ip_address(server.ip_address)
                    log = ServerLog(
                        server_id=None,
                        action="external_server_unreachable",
                        status="error",
                        message=f"Внешний сервер {server.name} ({masked_ip}) недоступен"
                    )
                    db.session.add(log)
                    
                    # Отправляем уведомление в Telegram только при изменении статуса
                    if status_changed:
                        from modules.telegram_notifier import TelegramNotifier
                        
                        TelegramNotifier.send_alert(
                            f"⚠️ ALERT: Внешний сервер {server.name} ({masked_ip}) недоступен!\n"
                            f"Время проверки: {datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S')}"
                        )
                        
                        logger.warning(f"Статус внешнего сервера {server.name} изменился: online -> offline")
                    else:
                        logger.warning(f"Внешний сервер {server.name} по-прежнему недоступен")
                
                db.session.commit()
            except Exception as e:
                logger.error(f"Ошибка при проверке внешнего сервера {server.name}: {str(e)}")
        
        logger.info(f"Проверка внешних серверов завершена. Всего: {results['total']}, "
                    f"Online: {results['online']}, Offline: {results['offline']}")
        return results