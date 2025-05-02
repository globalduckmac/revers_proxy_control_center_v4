import logging
import tempfile
import os
import time
import asyncio
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from models import Server, Domain, DomainGroup, ProxyConfig, ServerLog, db
from modules.server_manager import ServerManager
from modules.async_server_manager import AsyncServerManager

logger = logging.getLogger(__name__)

class DeploymentManager:
    """
    Handles the deployment process for proxy servers.
    """
    
    @staticmethod
    def deploy_nginx(server):
        """
        Deploy Nginx to a server.
        
        Args:
            server: Server model instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check connectivity first
            if not ServerManager.check_connectivity(server):
                logger.error(f"Cannot deploy Nginx to server {server.name}: Server is not reachable")
                return False
            
            # Create log entry for deployment start
            log = ServerLog(
                server_id=server.id,
                action='nginx_deployment',
                status='pending',
                message="Starting Nginx deployment"
            )
            db.session.add(log)
            db.session.commit()
            
            # Step 1: Update package lists (can take time)
            logger.info(f"Updating package lists on server {server.name}")
            try:
                ServerManager.execute_command(
                    server, 
                    "sudo apt-get update -q", 
                    long_running=True
                )
            except Exception as e:
                logger.warning(f"Package update warning on {server.name}: {str(e)}")
                # Continue anyway, might be just a repository error
            
            # Step 2: Install Nginx (long-running operation)
            logger.info(f"Installing Nginx on server {server.name}")
            try:
                stdout, stderr = ServerManager.execute_command(
                    server, 
                    "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx",
                    long_running=True
                )
            except Exception as e:
                logger.error(f"Nginx installation failed on {server.name}: {str(e)}")
                
                # Update log entry
                log.status = 'error'
                log.message = f"Failed to install Nginx: {str(e)}"
                db.session.commit()
                
                return False
            
            # Step 3: Verify Nginx installation
            logger.info(f"Verifying Nginx installation on server {server.name}")
            try:
                stdout, stderr = ServerManager.execute_command(
                    server,
                    "nginx -v"
                )
                
                if "nginx version" not in stderr:
                    logger.error(f"Nginx installation verification failed on server {server.name}")
                    
                    # Update log entry
                    log.status = 'error'
                    log.message = f"Nginx installation verification failed: {stderr}"
                    db.session.commit()
                    
                    return False
            except Exception as e:
                logger.error(f"Nginx verification failed on {server.name}: {str(e)}")
                
                # Update log entry
                log.status = 'error'
                log.message = f"Failed to verify Nginx installation: {str(e)}"
                db.session.commit()
                
                return False
            
            # Step 4: Enable and start Nginx service
            logger.info(f"Enabling and starting Nginx service on server {server.name}")
            try:
                ServerManager.execute_command(
                    server,
                    "sudo systemctl enable nginx"
                )
                
                ServerManager.execute_command(
                    server,
                    "sudo systemctl start nginx"
                )
            except Exception as e:
                logger.warning(f"Nginx service setup warning on {server.name}: {str(e)}")
                # Continue anyway, might work despite the error
            
            # Step 5: Create necessary directories
            logger.info(f"Creating Nginx configuration directories on server {server.name}")
            try:
                ServerManager.execute_command(
                    server,
                    "sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled"
                )
            except Exception as e:
                logger.warning(f"Nginx directory setup warning on {server.name}: {str(e)}")
                # Continue anyway, directories might already exist
            
            # Update log entry
            log.status = 'success'
            log.message = f"Nginx deployed successfully. Version: {stderr.strip()}"
            db.session.commit()
            
            logger.info(f"Successfully deployed Nginx to server {server.name}")
            return True
            
        except Exception as e:
            # Create error log entry
            try:
                error_log = ServerLog(
                    server_id=server.id,
                    action='nginx_deployment',
                    status='error',
                    message=f"Nginx deployment error: {str(e)}"
                )
                db.session.add(error_log)
                db.session.commit()
            except Exception as log_error:
                logger.error(f"Failed to create error log: {str(log_error)}")
                
            logger.error(f"Error deploying Nginx to server {server.name}: {str(e)}")
            return False
    
    @staticmethod
    def setup_ssl_certbot(server, domains):
        """
        Set up SSL certificates using Certbot for the specified domains.
        
        Args:
            server: Server model instance
            domains: List of Domain model instances or a single Domain instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Если передан один домен (не список), конвертируем его в список для унификации кода
        if not isinstance(domains, list):
            domains = [domains]
        try:
            # Check connectivity first
            if not ServerManager.check_connectivity(server):
                logger.error(f"Cannot set up SSL for server {server.name}: Server is not reachable")
                return False
            
            # Create log entry
            log = ServerLog(
                server_id=server.id,
                action='ssl_setup',
                status='pending',
                message=f"Setting up SSL for {len(domains)} domains"
            )
            db.session.add(log)
            db.session.commit()
            
            # Install Certbot and fix dependencies (long-running operation)
            logger.info(f"Installing Certbot on server {server.name}")
            try:
                # Обновляем систему
                ServerManager.execute_command(
                    server,
                    "sudo apt-get update -q", 
                    long_running=True
                )
                
                # Устанавливаем Certbot
                ServerManager.execute_command(
                    server,
                    "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx",
                    long_running=True
                )
                
                # Загружаем скрипт для исправления зависимостей
                fix_script_content = '''#!/bin/bash
# Удаляем конфликтующие пакеты
pip3 uninstall -y requests requests-toolbelt urllib3

# Устанавливаем совместимые версии
pip3 install requests==2.25.1
pip3 install urllib3==1.26.6
pip3 install requests-toolbelt==0.9.1
'''
                temp_file = "/tmp/fix_certbot_deps.sh"
                
                # Загружаем и выполняем скрипт
                ServerManager.upload_string_to_file(server, fix_script_content, temp_file)
                ServerManager.execute_command(server, f"chmod +x {temp_file}")
                ServerManager.execute_command(server, f"sudo bash {temp_file}", long_running=True)
                
                # Удаляем временный файл
                ServerManager.execute_command(server, f"rm {temp_file}")
                
                logger.info(f"Fixed Certbot dependencies on server {server.name}")
            except Exception as e:
                logger.warning(f"Certbot installation warning on {server.name}: {str(e)}")
                # Continue anyway, might be just a transient error
            
            # Get list of domains that need SSL
            ssl_domains = [d for d in domains if d.ssl_enabled]
            
            if not ssl_domains:
                log.status = 'success'
                log.message = "No domains with SSL enabled found"
                db.session.commit()
                return True
            
            # Get admin email from config or use a default
            from flask import current_app
            admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
            
            # Generate certification command
            domain_args = " ".join([f"-d {d.name}" for d in ssl_domains])
            cert_command = f"sudo certbot --nginx --expand --non-interactive --agree-tos --email {admin_email} {domain_args}"
            
            # Запуск операции выпуска сертификата в фоновом режиме
            # Создаем скрипт, который будет выполнять операцию и записывать результаты в файл
            result_file = f"/tmp/certbot_result_{int(time.time())}.txt"
            
            # Содержимое скрипта для запуска Certbot в фоне
            background_script = f'''#!/bin/bash
# Запускаем Certbot и записываем результаты в файл
{cert_command} > {result_file} 2>&1
echo $? >> {result_file}
'''
            
            # Создаем временный файл для скрипта
            script_file = f"/tmp/certbot_script_{int(time.time())}.sh"
            
            # Загружаем скрипт на сервер
            ServerManager.upload_string_to_file(server, background_script, script_file)
            ServerManager.execute_command(server, f"chmod +x {script_file}")
            
            # Запускаем скрипт в фоновом режиме
            logger.info(f"Starting background Certbot process for {len(ssl_domains)} domains on server {server.name}")
            ServerManager.execute_command(server, f"nohup bash {script_file} > /dev/null 2>&1 &")
            
            # Обновляем статус в базе данных
            log.status = 'processing'
            log.message = f"SSL certificate acquisition started in background mode for {len(ssl_domains)} domains. Check server logs for progress."
            db.session.commit()
            
            # Оповещаем пользователя
            logger.info(f"SSL certificate acquisition started in background mode for server {server.name}")
            
            # Возвращаем успешный статус, так как операция запущена в фоне
            return True
        
        except Exception as e:
            # Create error log entry for SSL setup
            try:
                error_log = ServerLog(
                    server_id=server.id,
                    action='ssl_setup',
                    status='error',
                    message=f"SSL setup error: {str(e)}"
                )
                db.session.add(error_log)
                db.session.commit()
            except Exception as log_error:
                logger.error(f"Failed to create SSL error log: {str(log_error)}")
                
            logger.error(f"Error setting up SSL on server {server.name}: {str(e)}")
            return False
            
    @staticmethod
    async def async_setup_ssl_certbot(server, domains, websocket=None):
        """
        Set up SSL certificates using Certbot for the specified domains with real-time output.
        
        Args:
            server: Server model instance
            domains: List of Domain model instances or a single Domain instance
            websocket: Optional WebSocket instance for real-time updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not isinstance(domains, list):
            domains = [domains]
        
        try:
            # Check connectivity first
            if not ServerManager.check_connectivity(server):
                error_msg = f"Cannot set up SSL for server {server.name}: Server is not reachable"
                logger.error(error_msg)
                if websocket:
                    await websocket.send_json({
                        "status": "error",
                        "step": "connectivity_check",
                        "message": error_msg
                    })
                return False
            
            # Create log entry
            log = ServerLog(
                server_id=server.id,
                action='ssl_setup',
                status='pending',
                message=f"Setting up SSL for {len(domains)} domains"
            )
            db.session.add(log)
            db.session.commit()
            
            if websocket:
                await websocket.send_json({
                    "status": "info",
                    "step": "initialization",
                    "message": f"Starting SSL setup for {len(domains)} domains on server {server.name}"
                })
            
            # Install Certbot and dependencies
            if websocket:
                await websocket.send_json({
                    "status": "info",
                    "step": "install_certbot",
                    "message": f"Installing Certbot on server {server.name}..."
                })
            
            try:
                if websocket:
                    await websocket.send_json({
                        "status": "info",
                        "step": "update_system",
                        "message": "Updating package lists..."
                    })
                
                update_result = await AsyncServerManager.execute_command_streaming(
                    server,
                    "sudo apt-get update -q",
                    callback=websocket.send_json if websocket else None
                )
                
                if websocket:
                    await websocket.send_json({
                        "status": "info",
                        "step": "update_system",
                        "message": "Package lists updated",
                        "complete": True
                    })
                
                # Install Certbot
                if websocket:
                    await websocket.send_json({
                        "status": "info",
                        "step": "install_certbot",
                        "message": "Installing Certbot and Nginx plugin..."
                    })
                
                certbot_result = await AsyncServerManager.execute_command_streaming(
                    server,
                    "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx",
                    callback=websocket.send_json if websocket else None
                )
                
                if websocket:
                    await websocket.send_json({
                        "status": "info",
                        "step": "install_certbot",
                        "message": "Certbot installed successfully",
                        "complete": True
                    })
                
                if websocket:
                    await websocket.send_json({
                        "status": "info",
                        "step": "fix_dependencies",
                        "message": "Fixing Certbot dependencies..."
                    })
                
                fix_script_content = '''#!/bin/bash
pip3 uninstall -y requests requests-toolbelt urllib3

# Install compatible versions
pip3 install requests==2.25.1
pip3 install urllib3==1.26.6
pip3 install requests-toolbelt==0.9.1
'''
                temp_file = "/tmp/fix_certbot_deps.sh"
                
                await AsyncServerManager.upload_string_to_file(server, fix_script_content, temp_file)
                await AsyncServerManager.execute_command(server, f"chmod +x {temp_file}")
                
                fix_result = await AsyncServerManager.execute_command_streaming(
                    server,
                    f"sudo bash {temp_file}",
                    callback=websocket.send_json if websocket else None
                )
                
                await AsyncServerManager.execute_command(server, f"rm {temp_file}")
                
                if websocket:
                    await websocket.send_json({
                        "status": "info",
                        "step": "fix_dependencies",
                        "message": "Dependencies fixed successfully",
                        "complete": True
                    })
                
            except Exception as e:
                error_msg = f"Certbot installation warning on {server.name}: {str(e)}"
                logger.warning(error_msg)
                if websocket:
                    await websocket.send_json({
                        "status": "warning",
                        "step": "install_certbot",
                        "message": error_msg
                    })
            
            # Get list of domains that need SSL
            ssl_domains = [d for d in domains if d.ssl_enabled]
            
            if not ssl_domains:
                complete_msg = "No domains with SSL enabled found"
                log.status = 'success'
                log.message = complete_msg
                db.session.commit()
                
                if websocket:
                    await websocket.send_json({
                        "status": "success",
                        "step": "complete",
                        "message": complete_msg
                    })
                
                return True
            
            # Get admin email from config or use a default
            from flask import current_app
            admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
            
            if websocket:
                await websocket.send_json({
                    "status": "info",
                    "step": "domain_verification",
                    "message": "Verifying DNS for domains..."
                })
            
            for domain in ssl_domains:
                verify_command = f"dig +short {domain.name} | grep -q '{server.ip_address}' && echo 'OK' || echo 'FAIL'"
                verify_result = await AsyncServerManager.execute_command(server, verify_command, capture_output=True)
                
                if websocket:
                    status = "success" if "OK" in verify_result else "warning"
                    await websocket.send_json({
                        "status": status,
                        "step": "domain_verification",
                        "message": f"Domain {domain.name}: {'DNS verified' if 'OK' in verify_result else 'DNS verification failed - certificate might fail'}"
                    })
            
            # Generate certification command
            domain_args = " ".join([f"-d {d.name}" for d in ssl_domains])
            cert_command = f"sudo certbot --nginx --expand --non-interactive --agree-tos --email {admin_email} {domain_args}"
            
            if websocket:
                await websocket.send_json({
                    "status": "info",
                    "step": "certificate_request",
                    "message": f"Requesting certificates for {len(ssl_domains)} domains..."
                })
            
            cert_result = await AsyncServerManager.execute_command_streaming(
                server,
                cert_command,
                callback=websocket.send_json if websocket else None
            )
            
            if cert_result.get('exit_code', 1) == 0:
                success_msg = f"SSL certificates successfully issued for {len(ssl_domains)} domains"
                log.status = 'success'
                log.message = success_msg
                db.session.commit()
                
                if websocket:
                    await websocket.send_json({
                        "status": "success",
                        "step": "complete",
                        "message": success_msg
                    })
                
                return True
            else:
                error_msg = f"SSL certificate issuance failed: {cert_result.get('error', 'Unknown error')}"
                log.status = 'error'
                log.message = error_msg
                db.session.commit()
                
                if websocket:
                    await websocket.send_json({
                        "status": "error",
                        "step": "complete",
                        "message": error_msg
                    })
                
                return False
                
        except Exception as e:
            # Create error log entry for SSL setup
            try:
                error_log = ServerLog(
                    server_id=server.id,
                    action='ssl_setup',
                    status='error',
                    message=f"SSL setup error: {str(e)}"
                )
                db.session.add(error_log)
                db.session.commit()
            except Exception as log_error:
                logger.error(f"Failed to create SSL error log: {str(log_error)}")
                
            error_msg = f"Error setting up SSL on server {server.name}: {str(e)}"
            logger.error(error_msg)
            
            if websocket:
                await websocket.send_json({
                    "status": "error",
                    "step": "complete",
                    "message": error_msg
                })
                
            return False
