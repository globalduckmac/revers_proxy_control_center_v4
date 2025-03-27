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
    def install_glances(server_id, api_port=None, web_port=None):
        """
        Начинает асинхронную установку Glances на указанный сервер с Ubuntu 22.04.
        Использует стандартный порт 61208 для API и веб-интерфейса.
        Обновляет статус сервера на 'installing' и возвращает результат.
        
        Args:
            server_id: ID сервера
            api_port: (не используется, оставлено для совместимости)
            web_port: (не используется, оставлено для совместимости)
            
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
    def _install_glances_worker(server_id, api_port=None, web_port=None):
        """
        Рабочая функция для асинхронной установки Glances на указанный сервер с Ubuntu 22.04.
        Использует стандартный порт 61208 для API и веб-интерфейса.
        Вызывается в отдельном потоке.
        
        Args:
            server_id: ID сервера
            api_port: (не используется, оставлено для совместимости)
            web_port: (не используется, оставлено для совместимости)
        """
        from app import app
        with app.app_context():
            logger.info(f"Установка Glances на сервер ID {server_id}, API порт: {api_port}, Web порт: {web_port}")
            
            server = Server.query.get(server_id)
            if not server:
                logger.error(f'Сервер с ID {server_id} не найден')
                return
            
            try:
                # Шаг 1: Получаем скрипт установки из локальной файловой системы для Ubuntu 22.04
                install_script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'install_glances_ubuntu22.sh')
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
                remote_script_path = '/tmp/install_glances_ubuntu22.sh'
                sftp.putfo(open(install_script_path, 'rb'), remote_script_path)
                sftp.chmod(remote_script_path, 0o755)  # Делаем скрипт исполняемым
                sftp.close()
                
                # Шаг 4: Запускаем скрипт установки
                logger.info(f"Запуск скрипта установки на сервере {server.ip_address}")
                command = f"sudo bash {remote_script_path}"
                stdin, stdout, stderr = ssh.exec_command(command)
                exit_status = stdout.channel.recv_exit_status()
                
                # Шаг 5: Получаем вывод скрипта
                stdout_data = stdout.read().decode('utf-8')
                stderr_data = stderr.read().decode('utf-8')
                
                # Шаг 6: Обновляем информацию о сервере в базе данных
                if exit_status == 0:
                    server.glances_installed = True
                    server.glances_port = 61208
                    server.glances_web_port = 61208
                    server.glances_enabled = True
                    server.glances_status = 'active'
                    server.glances_last_check = datetime.datetime.now()
                    
                    # Логируем успешную установку
                    log = ServerLog(
                        server_id=server.id,
                        action='install_glances',
                        status='success',
                        message=f'Glances успешно установлен. API и веб-интерфейс доступны на порту 61208\n\nВывод:\n{stdout_data}'
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
    def diagnose_glances_installation(server_id):
        """
        Запускает полную диагностику проблем с Glances на сервере, включая все возможные
        причины недоступности API и проблем с запуском.
        
        Args:
            server_id: ID сервера
            
        Returns:
            dict: Результаты диагностики {'success': bool, 'details': list, 'summary': str}
        """
        logger.info(f"Запуск диагностики Glances на сервере ID {server_id}")
        
        server = Server.query.get(server_id)
        if not server:
            return {'success': False, 'summary': f'Сервер с ID {server_id} не найден'}
        
        if not server.glances_installed and server.glances_status != 'installing':
            return {'success': False, 'summary': 'Glances не установлен на этом сервере'}
        
        try:
            # Подключаемся к серверу
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
                return {'success': False, 'summary': 'Не найдены учетные данные SSH для подключения к серверу'}
            
            ssh.connect(**connect_kwargs)
            
            # Собираем результаты диагностики
            results = {
                'success': True,
                'details': [],
                'fixes_applied': [],
                'service_running': False,
                'api_accessible': False,
                'summary': ''
            }
            
            # 1. Проверяем установлен ли glances
            stdin, stdout, stderr = ssh.exec_command("which glances || echo 'not found'")
            glances_path = stdout.read().decode('utf-8').strip()
            
            if 'not found' in glances_path:
                results['details'].append({
                    'test': 'Проверка установки Glances',
                    'status': 'error',
                    'message': 'Команда glances не найдена в системе'
                })
            else:
                results['details'].append({
                    'test': 'Проверка установки Glances',
                    'status': 'success',
                    'message': f'Glances установлен: {glances_path}'
                })
                
                # Проверка версии
                stdin, stdout, stderr = ssh.exec_command("glances --version || echo 'error'")
                glances_version = stdout.read().decode('utf-8').strip()
                
                results['details'].append({
                    'test': 'Версия Glances',
                    'status': 'info',
                    'message': f'Версия: {glances_version}'
                })
            
            # 2. Проверка статуса сервиса systemd
            stdin, stdout, stderr = ssh.exec_command("systemctl status glances.service || echo 'no systemd service'")
            systemd_status = stdout.read().decode('utf-8').strip()
            systemd_error = stderr.read().decode('utf-8').strip()
            
            systemd_running = False
            if 'Active: active (running)' in systemd_status:
                systemd_running = True
                results['service_running'] = True
                results['details'].append({
                    'test': 'Systemd сервис',
                    'status': 'success',
                    'message': 'Сервис glances.service активен и работает'
                })
            elif 'no systemd service' in systemd_status:
                results['details'].append({
                    'test': 'Systemd сервис',
                    'status': 'warning',
                    'message': 'Сервис glances.service не найден'
                })
            else:
                results['details'].append({
                    'test': 'Systemd сервис',
                    'status': 'error',
                    'message': f'Сервис glances.service не работает: {systemd_status}\n{systemd_error}'
                })
            
            # 3. Проверка статуса supervisor
            stdin, stdout, stderr = ssh.exec_command("supervisorctl status glances || echo 'no supervisor'")
            supervisor_status = stdout.read().decode('utf-8').strip()
            
            supervisor_running = False
            if 'RUNNING' in supervisor_status:
                supervisor_running = True
                results['service_running'] = True
                results['details'].append({
                    'test': 'Supervisor',
                    'status': 'success',
                    'message': 'Glances запущен через supervisor'
                })
            elif 'no supervisor' in supervisor_status:
                results['details'].append({
                    'test': 'Supervisor',
                    'status': 'warning',
                    'message': 'Supervisor не настроен для Glances'
                })
            else:
                results['details'].append({
                    'test': 'Supervisor',
                    'status': 'error',
                    'message': f'Glances не запущен через supervisor: {supervisor_status}'
                })
            
            # 4. Проверка процессов
            stdin, stdout, stderr = ssh.exec_command("ps aux | grep -v grep | grep 'glances -w' | wc -l")
            process_count = int(stdout.read().decode('utf-8').strip())
            
            if process_count > 0:
                results['service_running'] = True
                results['details'].append({
                    'test': 'Процессы',
                    'status': 'success',
                    'message': f'Найдено {process_count} процессов Glances'
                })
                
                # Получаем детали процессов
                stdin, stdout, stderr = ssh.exec_command("ps aux | grep -v grep | grep 'glances -w'")
                process_details = stdout.read().decode('utf-8').strip()
                results['details'].append({
                    'test': 'Детали процессов',
                    'status': 'info',
                    'message': process_details
                })
            else:
                results['details'].append({
                    'test': 'Процессы',
                    'status': 'error',
                    'message': 'Не найдено запущенных процессов Glances'
                })
            
            # 5. Проверка портов
            stdin, stdout, stderr = ssh.exec_command(f"ss -tulpn | grep ':{server.glances_port}' || netstat -tulpn 2>/dev/null | grep ':{server.glances_port}' || echo 'port not in use'")
            api_port_status = stdout.read().decode('utf-8').strip()
            
            if 'port not in use' not in api_port_status:
                results['details'].append({
                    'test': f'Прослушивание порта API ({server.glances_port})',
                    'status': 'success',
                    'message': f'Порт {server.glances_port} прослушивается: {api_port_status}'
                })
            else:
                results['details'].append({
                    'test': f'Прослушивание порта API ({server.glances_port})',
                    'status': 'error',
                    'message': f'Порт {server.glances_port} не прослушивается'
                })
            
            stdin, stdout, stderr = ssh.exec_command(f"ss -tulpn | grep ':{server.glances_web_port}' || netstat -tulpn 2>/dev/null | grep ':{server.glances_web_port}' || echo 'port not in use'")
            web_port_status = stdout.read().decode('utf-8').strip()
            
            if 'port not in use' not in web_port_status:
                results['details'].append({
                    'test': f'Прослушивание веб-порта ({server.glances_web_port})',
                    'status': 'success',
                    'message': f'Порт {server.glances_web_port} прослушивается: {web_port_status}'
                })
            else:
                results['details'].append({
                    'test': f'Прослушивание веб-порта ({server.glances_web_port})',
                    'status': 'error',
                    'message': f'Порт {server.glances_web_port} не прослушивается'
                })
            
            # 6. Проверка доступности API через curl
            stdin, stdout, stderr = ssh.exec_command(f"curl -s http://localhost:{server.glances_port}/api/3/cpu 2>/dev/null | head -20 || echo 'API not accessible'")
            api_response = stdout.read().decode('utf-8').strip()
            
            if 'API not accessible' not in api_response and api_response != '':
                results['api_accessible'] = True
                results['details'].append({
                    'test': 'API доступность',
                    'status': 'success',
                    'message': f'API доступен через localhost:{server.glances_port}. Ответ: {api_response[:100]}...'
                })
            else:
                results['details'].append({
                    'test': 'API доступность',
                    'status': 'error',
                    'message': f'API недоступен через localhost:{server.glances_port}'
                })
                
                # Проверяем через 0.0.0.0
                stdin, stdout, stderr = ssh.exec_command(f"curl -s http://0.0.0.0:{server.glances_port}/api/3/cpu 2>/dev/null | head -20 || echo 'API not accessible'")
                api_response = stdout.read().decode('utf-8').strip()
                
                if 'API not accessible' not in api_response and api_response != '':
                    results['api_accessible'] = True
                    results['details'].append({
                        'test': 'API доступность (0.0.0.0)',
                        'status': 'success',
                        'message': f'API доступен через 0.0.0.0:{server.glances_port}'
                    })
                
                # Проверяем через IP сервера
                stdin, stdout, stderr = ssh.exec_command(f"curl -s http://{server.ip_address}:{server.glances_port}/api/3/cpu 2>/dev/null | head -20 || echo 'API not accessible'")
                api_response = stdout.read().decode('utf-8').strip()
                
                if 'API not accessible' not in api_response and api_response != '':
                    results['api_accessible'] = True
                    results['details'].append({
                        'test': 'API доступность (IP)',
                        'status': 'success',
                        'message': f'API доступен через {server.ip_address}:{server.glances_port}'
                    })
            
            # 7. Проверка файрвола
            stdin, stdout, stderr = ssh.exec_command("which ufw >/dev/null && ufw status || echo 'ufw not found'")
            ufw_status = stdout.read().decode('utf-8').strip()
            
            if 'ufw not found' not in ufw_status:
                results['details'].append({
                    'test': 'Файрвол UFW',
                    'status': 'info',
                    'message': f'Статус UFW: {ufw_status}'
                })
                
                # Проверяем правила для портов Glances
                stdin, stdout, stderr = ssh.exec_command(f"ufw status | grep {server.glances_port} || echo 'no rule found'")
                ufw_api_rule = stdout.read().decode('utf-8').strip()
                
                if 'no rule found' not in ufw_api_rule:
                    results['details'].append({
                        'test': f'Правило UFW для порта {server.glances_port}',
                        'status': 'success',
                        'message': f'Найдено правило: {ufw_api_rule}'
                    })
                else:
                    results['details'].append({
                        'test': f'Правило UFW для порта {server.glances_port}',
                        'status': 'warning',
                        'message': f'Не найдено правило UFW для порта {server.glances_port}'
                    })
                    
                    # Если порт не открыт, добавляем его
                    if not results['api_accessible']:
                        stdin, stdout, stderr = ssh.exec_command(f"sudo ufw allow {server.glances_port}/tcp || echo 'failed to add rule'")
                        ufw_add_result = stdout.read().decode('utf-8').strip()
                        
                        if 'failed to add rule' not in ufw_add_result:
                            results['fixes_applied'].append(f'Добавлено правило UFW для порта {server.glances_port}')
                        
                        stdin, stdout, stderr = ssh.exec_command(f"sudo ufw allow {server.glances_web_port}/tcp || echo 'failed to add rule'")
                        ufw_add_result = stdout.read().decode('utf-8').strip()
                        
                        if 'failed to add rule' not in ufw_add_result:
                            results['fixes_applied'].append(f'Добавлено правило UFW для порта {server.glances_web_port}')
            
            # 8. Файл конфигурации
            stdin, stdout, stderr = ssh.exec_command("cat /etc/glances/glances.conf 2>/dev/null || echo 'config not found'")
            config_content = stdout.read().decode('utf-8').strip()
            
            if 'config not found' not in config_content:
                results['details'].append({
                    'test': 'Конфигурация',
                    'status': 'success',
                    'message': 'Найден файл конфигурации /etc/glances/glances.conf'
                })
                
                # Проверяем настройки веб и API
                if 'host = 0.0.0.0' in config_content:
                    results['details'].append({
                        'test': 'Настройка хоста',
                        'status': 'success',
                        'message': 'Настроено прослушивание на всех интерфейсах (0.0.0.0)'
                    })
                else:
                    results['details'].append({
                        'test': 'Настройка хоста',
                        'status': 'warning',
                        'message': 'Не настроено прослушивание на всех интерфейсах. Может быть проблема доступа извне.'
                    })
            else:
                results['details'].append({
                    'test': 'Конфигурация',
                    'status': 'warning',
                    'message': 'Не найден файл конфигурации /etc/glances/glances.conf'
                })
            
            # 9. Попытка перезапуска, если сервис не работает
            if not results['service_running']:
                restart_commands = [
                    "sudo systemctl restart glances.service || echo 'failed'",
                    "sudo supervisorctl restart glances || echo 'failed'",
                    f"sudo pkill -f 'glances -w' || echo 'no process killed'; sudo nohup /usr/local/bin/glances -w -s --bind 0.0.0.0 --port {server.glances_port} --webserver-port {server.glances_web_port} > /var/log/glances_nohup.log 2>&1 &"
                ]
                
                for cmd in restart_commands:
                    stdin, stdout, stderr = ssh.exec_command(cmd)
                    restart_result = stdout.read().decode('utf-8').strip()
                    if 'failed' not in restart_result:
                        results['fixes_applied'].append(f'Выполнена попытка перезапуска: {cmd}')
                
                # Проверяем снова
                stdin, stdout, stderr = ssh.exec_command("ps aux | grep -v grep | grep 'glances -w' | wc -l")
                process_count = int(stdout.read().decode('utf-8').strip())
                
                if process_count > 0:
                    results['service_running'] = True
                    results['fixes_applied'].append('Успешно запущен процесс Glances после перезапуска')
            
            # 10. Обновляем статус сервера в базе данных
            if results['api_accessible']:
                server.glances_status = 'active'
            elif results['service_running']:
                server.glances_status = 'service_running'
            else:
                server.glances_status = 'error'
                
            server.glances_last_check = datetime.datetime.now()
            db.session.commit()
            
            # Формируем итоговое сообщение
            if results['api_accessible']:
                results['summary'] = 'API Glances доступен и работает нормально.'
            elif results['service_running']:
                results['summary'] = 'Сервис Glances запущен, но API недоступен. Возможно проблемы с сетью или файрволом.'
            else:
                results['summary'] = 'Сервис Glances не запущен. Требуется ручная проверка на сервере.'
                
            if results['fixes_applied']:
                results['summary'] += f' Применены исправления: {", ".join(results["fixes_applied"])}'
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при диагностике Glances на сервере ID {server_id}: {str(e)}")
            return {
                'success': False,
                'summary': f'Ошибка при диагностике: {str(e)}',
                'details': []
            }
    
    @staticmethod
    def check_glances_status(server_id):
        """
        Проверяет статус Glances на указанном сервере с Ubuntu 22.04.
        Проверяет статус systemd сервиса и доступность API.
        
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
            
            # Шаг 2: Проверяем, запущен ли сервис Glances через systemd (оптимизировано для Ubuntu 22.04)
            command = "sudo systemctl is-active glances.service 2>/dev/null || echo 'inactive'"
            stdin, stdout, stderr = ssh.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8').strip()
            
            service_running = (exit_status == 0 and stdout_data == "active")
            
            # Если сервис не запущен, пробуем запустить его через systemd (оптимизировано для Ubuntu 22.04)
            if not service_running:
                logger.warning(f"Сервис Glances не запущен на сервере {server_id}, пробуем запустить")
                restart_command = f"sudo systemctl restart glances.service || echo 'Ошибка запуска systemd'"
                ssh.exec_command(restart_command)
                # Даем время для запуска
                import time
                time.sleep(5)
                
                # Проверяем статус еще раз (оптимизировано для Ubuntu 22.04, используя systemd)
                command = "sudo systemctl is-active glances.service 2>/dev/null && echo 'running'"
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
        Перезапускает сервис Glances на удаленном сервере с Ubuntu 22.04.
        Использует systemd для управления сервисом.
        
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
            
            # Шаг 2: Перезапускаем сервис Glances через systemd (основной метод для Ubuntu 22.04)
            commands = [
                "sudo systemctl restart glances.service || echo 'Ошибка перезапуска systemd'"
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