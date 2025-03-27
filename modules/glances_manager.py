"""
Модуль для управления и взаимодействия с Glances на удаленных серверах.
Позволяет устанавливать, проверять и получать данные с Glances.
"""

import logging
import json
import os
import datetime
import requests
from paramiko import SSHClient, AutoAddPolicy
from models import db, Server, ServerLog

# Настройка логирования
logger = logging.getLogger(__name__)

class GlancesManager:
    """
    Менеджер для работы с Glances на удаленных серверах.
    Предоставляет функционал для установки, проверки и получения данных.
    """
    
    @staticmethod
    def install_glances(server_id, api_port=61208, web_port=61209):
        """
        Начинает асинхронную установку Glances на указанный сервер.
        Обновляет статус сервера на 'installing' и возвращает результат.
        
        Args:
            server_id: ID сервера
            api_port: Порт для API Glances (по умолчанию 61208)
            web_port: Порт для веб-интерфейса Glances (по умолчанию 61209)
            
        Returns:
            dict: Результат запуска установки {'success': bool, 'message': str}
        """
        logger.info(f"Начинаем асинхронную установку Glances на сервер ID {server_id}, API порт: {api_port}, Web порт: {web_port}")
        
        server = Server.query.get(server_id)
        if not server:
            return {'success': False, 'message': f'Сервер с ID {server_id} не найден'}
        
        # Обновляем статус
        server.glances_status = 'installing'
        
        # Логируем начало установки
        log = ServerLog(
            server_id=server.id,
            action='install_glances_start',
            status='pending',
            message=f'Начата установка Glances. API порт: {api_port}, Web порт: {web_port}'
        )
        db.session.add(log)
        db.session.commit()
        
        # Запускаем установку в отдельном потоке
        from threading import Thread
        thread = Thread(
            target=GlancesManager._install_glances_worker,
            args=(server_id, api_port, web_port)
        )
        thread.daemon = True
        thread.start()
        
        return {
            'success': True,
            'message': 'Установка Glances запущена. Проверьте статус позже.',
            'status': 'installing'
        }
    
    @staticmethod
    def _install_glances_worker(server_id, api_port=61208, web_port=61209):
        """
        Рабочая функция для асинхронной установки Glances на указанный сервер.
        Вызывается в отдельном потоке.
        
        Args:
            server_id: ID сервера
            api_port: Порт для API Glances
            web_port: Порт для веб-интерфейса Glances
        """
        from app import app
        with app.app_context():
            logger.info(f"Установка Glances на сервер ID {server_id}, API порт: {api_port}, Web порт: {web_port}")
            
            server = Server.query.get(server_id)
            if not server:
                logger.error(f'Сервер с ID {server_id} не найден')
                return
            
            try:
                # Шаг 1: Получаем скрипт установки из локальной файловой системы
                install_script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'install_glances.sh')
                with open(install_script_path, 'r') as f:
                    install_script = f.read()
                
                # Шаг 2: Подключаемся к серверу по SSH
                ssh = SSHClient()
                ssh.set_missing_host_key_policy(AutoAddPolicy())
                
                # Подключаемся с использованием пароля или ключа
                connect_kwargs = {
                    'hostname': server.ip_address,
                    'username': server.ssh_user,
                    'port': server.ssh_port,
                    'timeout': 30
                }
                
                if server.ssh_key:
                    connect_kwargs['key_filename'] = server.get_key_file_path()
                elif server.ssh_password_hash:
                    connect_kwargs['password'] = server.get_decrypted_password()
                else:
                    logger.error(f'Не найдены учетные данные SSH для подключения к серверу {server_id}')
                    
                    # Обновляем статус сервера
                    server.glances_status = 'error'
                    server.glances_last_check = datetime.datetime.now()
                    
                    # Логируем ошибку
                    log = ServerLog(
                        server_id=server.id,
                        action='install_glances',
                        status='error',
                        message='Не найдены учетные данные SSH для подключения к серверу'
                    )
                    db.session.add(log)
                    db.session.commit()
                    return
                
                logger.debug(f"Подключение к серверу {server.ip_address}:{server.ssh_port} как {server.ssh_user}")
                ssh.connect(**connect_kwargs)
                
                # Шаг 3: Загружаем скрипт установки на сервер
                sftp = ssh.open_sftp()
                remote_script_path = '/tmp/install_glances.sh'
                sftp.putfo(open(install_script_path, 'rb'), remote_script_path)
                sftp.chmod(remote_script_path, 0o755)  # Делаем скрипт исполняемым
                sftp.close()
                
                # Шаг 4: Запускаем скрипт установки
                logger.info(f"Запуск скрипта установки на сервере {server.ip_address}")
                command = f"sudo bash {remote_script_path} {api_port} {web_port}"
                stdin, stdout, stderr = ssh.exec_command(command)
                exit_status = stdout.channel.recv_exit_status()
                
                # Шаг 5: Получаем вывод скрипта
                stdout_data = stdout.read().decode('utf-8')
                stderr_data = stderr.read().decode('utf-8')
                
                # Шаг 6: Обновляем информацию о сервере в базе данных
                if exit_status == 0:
                    server.glances_installed = True
                    server.glances_port = api_port
                    server.glances_web_port = web_port
                    server.glances_enabled = True
                    server.glances_status = 'active'
                    server.glances_last_check = datetime.datetime.now()
                    
                    # Логируем успешную установку
                    log = ServerLog(
                        server_id=server.id,
                        action='install_glances',
                        status='success',
                        message=f'Glances успешно установлен. API порт: {api_port}, Web порт: {web_port}\n\nВывод:\n{stdout_data}'
                    )
                    db.session.add(log)
                    db.session.commit()
                    
                    logger.info(f"Glances успешно установлен на сервер ID {server_id}")
                else:
                    # Обновляем статус сервера
                    server.glances_status = 'error'
                    server.glances_last_check = datetime.datetime.now()
                    
                    # Логируем ошибку установки
                    log = ServerLog(
                        server_id=server.id,
                        action='install_glances',
                        status='error',
                        message=f'Ошибка установки Glances. Код: {exit_status}\n\nСтандартный вывод:\n{stdout_data}\n\nОшибки:\n{stderr_data}'
                    )
                    db.session.add(log)
                    db.session.commit()
                    
                    logger.error(f"Ошибка установки Glances на сервер ID {server_id}. Код: {exit_status}")
                    
            except Exception as e:
                logger.error(f"Исключение при установке Glances на сервер ID {server_id}: {str(e)}")
                
                # Обновляем статус сервера
                server.glances_status = 'error'
                server.glances_last_check = datetime.datetime.now()
                
                # Логируем исключение
                log = ServerLog(
                    server_id=server.id,
                    action='install_glances',
                    status='error',
                    message=f'Исключение при установке Glances: {str(e)}'
                )
                db.session.add(log)
                db.session.commit()
    
    @staticmethod
    def check_glances_status(server_id):
        """
        Проверяет статус Glances на указанном сервере.
        
        Args:
            server_id: ID сервера
            
        Returns:
            dict: Статус Glances {'success': bool, 'running': bool, 'api_accessible': bool, 'message': str}
        """
        logger.info(f"Проверка статуса Glances на сервере ID {server_id}")
        
        server = Server.query.get(server_id)
        if not server:
            return {'success': False, 'message': f'Сервер с ID {server_id} не найден'}
        
        if not server.glances_installed and server.glances_status != 'installing':
            return {'success': False, 'running': False, 'api_accessible': False, 'message': 'Glances не установлен на этом сервере'}
        
        # Если Glances в процессе установки, возвращаем соответствующий статус
        if server.glances_status == 'installing':
            return {
                'success': True,
                'running': False,
                'api_accessible': False,
                'message': 'Установка Glances в процессе. Пожалуйста, подождите.'
            }
        
        try:
            # Шаг 1: Подключаемся к серверу по SSH
            ssh = SSHClient()
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            
            connect_kwargs = {
                'hostname': server.ip_address,
                'username': server.ssh_user,
                'port': server.ssh_port,
                'timeout': 15
            }
            
            if server.ssh_key:
                connect_kwargs['key_filename'] = server.get_key_file_path()
            elif server.ssh_password_hash:
                connect_kwargs['password'] = server.get_decrypted_password()
            else:
                return {'success': False, 'running': False, 'api_accessible': False, 'message': 'Не найдены учетные данные SSH для подключения к серверу'}
            
            logger.debug(f"Подключение к серверу {server.ip_address}:{server.ssh_port} как {server.ssh_user}")
            ssh.connect(**connect_kwargs)
            
            # Шаг 2: Проверяем, запущен ли сервис Glances несколькими способами
            command = "sudo systemctl is-active glances.service 2>/dev/null || echo 'checking supervisor...' && sudo supervisorctl status glances 2>/dev/null | grep -q RUNNING && echo 'supervisor:running' || echo 'checking ps...' && ps aux | grep -v grep | grep -q 'glances -w -s' && echo 'ps:running'"
            stdin, stdout, stderr = ssh.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8').strip()
            
            service_running = (exit_status == 0 and 
                              (stdout_data == "active" or 
                               "supervisor:running" in stdout_data or 
                               "ps:running" in stdout_data))
            
            # Если сервис не запущен, пробуем запустить его
            if not service_running:
                logger.warning(f"Сервис Glances не запущен на сервере {server_id}, пробуем запустить")
                restart_command = f"sudo systemctl restart glances.service || sudo supervisorctl restart glances || nohup /usr/local/bin/glances -w -s --disable-plugin docker --bind {server.ip_address} --port {server.glances_port} --webserver-port {server.glances_web_port} > /var/log/glances_nohup.log 2>&1 &"
                ssh.exec_command(restart_command)
                # Даем время для запуска
                import time
                time.sleep(5)
                
                # Проверяем статус еще раз
                command = "sudo systemctl is-active glances.service 2>/dev/null || sudo supervisorctl status glances 2>/dev/null | grep -q RUNNING || ps aux | grep -v grep | grep -q 'glances -w -s' && echo 'running'"
                stdin, stdout, stderr = ssh.exec_command(command)
                stdout_data = stdout.read().decode('utf-8').strip()
                service_running = "running" in stdout_data
            
            # Шаг 3: Проверяем доступность API несколькими способами
            api_accessible = False
            
            # Сначала проверим простым curl
            command = f"curl -s http://localhost:{server.glances_port}/api/3/cpu 2>/dev/null | grep -q total"
            stdin, stdout, stderr = ssh.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            api_accessible = exit_status == 0
            
            # Если API недоступен через localhost, попробуем через 0.0.0.0 или IP сервера
            if not api_accessible:
                command = f"curl -s http://0.0.0.0:{server.glances_port}/api/3/cpu 2>/dev/null | grep -q total || curl -s http://{server.ip_address}:{server.glances_port}/api/3/cpu 2>/dev/null | grep -q total"
                stdin, stdout, stderr = ssh.exec_command(command)
                exit_status = stdout.channel.recv_exit_status()
                api_accessible = exit_status == 0
            
            # Если API все еще недоступен, проверим, слушает ли процесс нужный порт
            if not api_accessible:
                command = f"sudo netstat -tulpn | grep -q ':{server.glances_port}' || sudo ss -tulpn | grep -q ':{server.glances_port}'"
                stdin, stdout, stderr = ssh.exec_command(command)
                exit_status = stdout.channel.recv_exit_status()
                port_listening = exit_status == 0
                
                if port_listening:
                    # Порт слушается, но API не отвечает - возможно, Glances еще инициализируется
                    service_running = True
            
            # Шаг 4: Обновляем информацию о сервере в базе данных
            if api_accessible:
                server.glances_status = 'active'
            elif service_running:
                server.glances_status = 'service_running'
            else:
                server.glances_status = 'error'
                
            server.glances_last_check = datetime.datetime.now()
            db.session.commit()
            
            return {
                'success': True,
                'running': service_running,
                'api_accessible': api_accessible,
                'message': f"Glances {'запущен' if service_running else 'не запущен'}, API {'доступен' if api_accessible else 'недоступен'}"
            }
            
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса Glances: {str(e)}")
            
            # Обновляем статус сервера
            server.glances_status = 'error'
            server.glances_last_check = datetime.datetime.now()
            db.session.commit()
            
            # Логируем исключение
            log = ServerLog(
                server_id=server.id,
                action='check_glances_status',
                status='error',
                message=f'Исключение при проверке статуса Glances: {str(e)}'
            )
            db.session.add(log)
            db.session.commit()
            
            return {
                'success': False,
                'running': False,
                'api_accessible': False,
                'message': f'Ошибка при проверке статуса Glances: {str(e)}'
            }
    
    @staticmethod
    def collect_server_metrics(server_id):
        """
        Собирает метрики сервера с помощью Glances API.
        
        Args:
            server_id: ID сервера
            
        Returns:
            dict: Собранные метрики или информация об ошибке
        """
        logger.info(f"Сбор метрик с сервера ID {server_id}")
        
        server = Server.query.get(server_id)
        if not server:
            return {'success': False, 'message': f'Сервер с ID {server_id} не найден'}
        
        if not server.glances_installed or not server.glances_enabled:
            return {'success': False, 'message': 'Glances не установлен или отключен на этом сервере'}
        
        try:
            # Шаг 1: Проверяем доступность API
            glances_url = server.get_glances_url()
            if not glances_url:
                return {'success': False, 'message': 'Не удалось определить URL API Glances'}
            
            # Шаг 2: Запрашиваем основные метрики
            metrics = {
                'success': True,
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            # CPU
            cpu_response = requests.get(f"{glances_url}/api/3/cpu", timeout=5)
            if cpu_response.status_code == 200:
                cpu_data = cpu_response.json()
                metrics['cpu_usage'] = cpu_data.get('total', 0)
            else:
                metrics['cpu_usage'] = None
            
            # Память
            mem_response = requests.get(f"{glances_url}/api/3/mem", timeout=5)
            if mem_response.status_code == 200:
                mem_data = mem_response.json()
                metrics['memory_usage'] = mem_data.get('percent', 0)
                metrics['memory_total'] = mem_data.get('total', 0)
                metrics['memory_used'] = mem_data.get('used', 0)
            else:
                metrics['memory_usage'] = None
                metrics['memory_total'] = None
                metrics['memory_used'] = None
            
            # Диск
            fs_response = requests.get(f"{glances_url}/api/3/fs", timeout=5)
            if fs_response.status_code == 200:
                fs_data = fs_response.json()
                if fs_data and len(fs_data) > 0:
                    # Берем первый диск как основной (обычно корневой)
                    metrics['disk_usage'] = fs_data[0].get('percent', 0)
                    metrics['disk_total'] = fs_data[0].get('size', 0)
                    metrics['disk_used'] = fs_data[0].get('used', 0)
                else:
                    metrics['disk_usage'] = None
                    metrics['disk_total'] = None
                    metrics['disk_used'] = None
            else:
                metrics['disk_usage'] = None
                metrics['disk_total'] = None
                metrics['disk_used'] = None
            
            # Нагрузка
            load_response = requests.get(f"{glances_url}/api/3/load", timeout=5)
            if load_response.status_code == 200:
                load_data = load_response.json()
                metrics['load_avg_1min'] = load_data.get('min1', 0)
                metrics['load_avg_5min'] = load_data.get('min5', 0)
                metrics['load_avg_15min'] = load_data.get('min15', 0)
            else:
                metrics['load_avg_1min'] = None
                metrics['load_avg_5min'] = None
                metrics['load_avg_15min'] = None
            
            # Шаг 3: Обновляем информацию о сервере в базе данных
            server.glances_status = 'active'
            server.glances_last_check = datetime.datetime.now()
            db.session.commit()
            
            return metrics
            
        except Exception as e:
            logger.error(f"Ошибка при сборе метрик сервера: {str(e)}")
            
            # Логируем исключение
            log = ServerLog(
                server_id=server.id,
                action='collect_metrics',
                status='error',
                message=f'Исключение при сборе метрик: {str(e)}'
            )
            db.session.add(log)
            db.session.commit()
            
            return {
                'success': False,
                'message': f'Ошибка при сборе метрик: {str(e)}'
            }
    
    @staticmethod
    def restart_glances_service(server_id):
        """
        Перезапускает сервис Glances на удаленном сервере.
        
        Args:
            server_id: ID сервера
            
        Returns:
            dict: Результат операции {'success': bool, 'message': str}
        """
        logger.info(f"Перезапуск сервиса Glances на сервере ID {server_id}")
        
        server = Server.query.get(server_id)
        if not server:
            return {'success': False, 'message': f'Сервер с ID {server_id} не найден'}
        
        if not server.glances_installed:
            return {'success': False, 'message': 'Glances не установлен на этом сервере'}
        
        try:
            # Шаг 1: Подключаемся к серверу по SSH
            ssh = SSHClient()
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            
            connect_kwargs = {
                'hostname': server.ip_address,
                'username': server.ssh_user,
                'port': server.ssh_port,
                'timeout': 15
            }
            
            if server.ssh_key:
                connect_kwargs['key_filename'] = server.get_key_file_path()
            elif server.ssh_password_hash:
                connect_kwargs['password'] = server.get_decrypted_password()
            else:
                return {'success': False, 'message': 'Не найдены учетные данные SSH для подключения к серверу'}
            
            logger.debug(f"Подключение к серверу {server.ip_address}:{server.ssh_port} как {server.ssh_user}")
            ssh.connect(**connect_kwargs)
            
            # Шаг 2: Перезапускаем сервис Glances
            commands = [
                "sudo systemctl restart glances.service || true",
                "sudo supervisorctl restart glances || true"
            ]
            
            restart_success = False
            output = []
            
            for command in commands:
                stdin, stdout, stderr = ssh.exec_command(command)
                exit_status = stdout.channel.recv_exit_status()
                stdout_data = stdout.read().decode('utf-8').strip()
                stderr_data = stderr.read().decode('utf-8').strip()
                
                output.append(f"Command: {command}")
                output.append(f"Exit status: {exit_status}")
                output.append(f"Output: {stdout_data}")
                output.append(f"Errors: {stderr_data}")
                output.append("---")
                
                if exit_status == 0:
                    restart_success = True
            
            # Шаг 3: Проверяем статус после перезапуска
            status = GlancesManager.check_glances_status(server_id)
            
            # Шаг 4: Логируем результат
            if restart_success and status.get('running', False):
                log = ServerLog(
                    server_id=server.id,
                    action='restart_glances',
                    status='success',
                    message=f'Сервис Glances успешно перезапущен\n\n{chr(10).join(output)}'
                )
                db.session.add(log)
                db.session.commit()
                
                return {
                    'success': True,
                    'message': 'Сервис Glances успешно перезапущен',
                    'status': status
                }
            else:
                log = ServerLog(
                    server_id=server.id,
                    action='restart_glances',
                    status='error',
                    message=f'Не удалось перезапустить сервис Glances\n\n{chr(10).join(output)}'
                )
                db.session.add(log)
                db.session.commit()
                
                return {
                    'success': False,
                    'message': 'Не удалось перезапустить сервис Glances',
                    'status': status,
                    'output': output
                }
                
        except Exception as e:
            logger.error(f"Ошибка при перезапуске сервиса Glances: {str(e)}")
            
            # Логируем исключение
            log = ServerLog(
                server_id=server.id,
                action='restart_glances',
                status='error',
                message=f'Исключение при перезапуске сервиса Glances: {str(e)}'
            )
            db.session.add(log)
            db.session.commit()
            
            return {
                'success': False,
                'message': f'Ошибка при перезапуске сервиса Glances: {str(e)}'
            }
    
    @staticmethod
    def get_detailed_metrics(server_id):
        """
        Получает детальные метрики с сервера через Glances API.
        
        Args:
            server_id: ID сервера
            
        Returns:
            dict: Детальные метрики сервера
        """
        logger.info(f"Получение детальных метрик с сервера ID {server_id}")
        
        server = Server.query.get(server_id)
        if not server:
            return {'success': False, 'message': f'Сервер с ID {server_id} не найден'}
        
        if not server.glances_installed or not server.glances_enabled:
            return {'success': False, 'message': 'Glances не установлен или отключен на этом сервере'}
        
        try:
            # Шаг 1: Проверяем доступность API
            glances_url = server.get_glances_url()
            if not glances_url:
                return {'success': False, 'message': 'Не удалось определить URL API Glances'}
            
            # Шаг 2: Запрашиваем все доступные метрики
            try:
                # Информация о системе
                system_response = requests.get(f"{glances_url}/api/3/system", timeout=5)
                system_data = system_response.json() if system_response.status_code == 200 else {}
                
                # CPU
                cpu_response = requests.get(f"{glances_url}/api/3/cpu", timeout=5)
                cpu_data = cpu_response.json() if cpu_response.status_code == 200 else {}
                
                # Память
                mem_response = requests.get(f"{glances_url}/api/3/mem", timeout=5)
                mem_data = mem_response.json() if mem_response.status_code == 200 else {}
                
                # Swap
                memswap_response = requests.get(f"{glances_url}/api/3/memswap", timeout=5)
                memswap_data = memswap_response.json() if memswap_response.status_code == 200 else {}
                
                # Диски
                fs_response = requests.get(f"{glances_url}/api/3/fs", timeout=5)
                fs_data = fs_response.json() if fs_response.status_code == 200 else []
                
                # Нагрузка
                load_response = requests.get(f"{glances_url}/api/3/load", timeout=5)
                load_data = load_response.json() if load_response.status_code == 200 else {}
                
                # Сеть
                network_response = requests.get(f"{glances_url}/api/3/network", timeout=5)
                network_data = network_response.json() if network_response.status_code == 200 else {}
                
                # Процессы
                process_response = requests.get(f"{glances_url}/api/3/processlist", timeout=5)
                process_data = process_response.json() if process_response.status_code == 200 else []
                
                # Шаг 3: Объединяем все метрики в один объект
                metrics = {
                    'success': True,
                    'timestamp': datetime.datetime.now().isoformat(),
                    'system': system_data,
                    'cpu': cpu_data,
                    'mem': mem_data,
                    'memswap': memswap_data,
                    'fs': fs_data,
                    'load': load_data,
                    'network': network_data,
                    'processlist': process_data
                }
                
                # Шаг 4: Обновляем информацию о сервере в базе данных
                server.glances_status = 'active'
                server.glances_last_check = datetime.datetime.now()
                db.session.commit()
                
                return metrics
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка при запросе к API Glances: {str(e)}")
                
                # Обновляем статус сервера
                server.glances_status = 'error'
                server.glances_last_check = datetime.datetime.now()
                db.session.commit()
                
                return {
                    'success': False,
                    'message': f'Ошибка при запросе к API Glances: {str(e)}'
                }
            
        except Exception as e:
            logger.error(f"Ошибка при получении детальных метрик: {str(e)}")
            
            # Логируем исключение
            log = ServerLog(
                server_id=server.id,
                action='get_detailed_metrics',
                status='error',
                message=f'Исключение при получении детальных метрик: {str(e)}'
            )
            db.session.add(log)
            db.session.commit()
            
            return {
                'success': False,
                'message': f'Ошибка при получении детальных метрик: {str(e)}'
            }