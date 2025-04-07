import os
import logging
import tempfile
import json
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from threading import Thread
from flask import current_app
from models import Server, Domain, DomainGroup, ProxyConfig, ServerLog, db
from modules.server_manager import ServerManager
from modules.domain_manager import DomainManager

logger = logging.getLogger(__name__)

class ProxyManager:
    """
    Handles operations related to proxy configuration generation and deployment.
    """
    
    def __init__(self, templates_path):
        """
        Initialize the ProxyManager with templates path.
        
        Args:
            templates_path: Path to the directory containing Nginx templates
        """
        self.templates_path = templates_path
        self.jinja_env = Environment(loader=FileSystemLoader(templates_path))
        
        # Add datetime function for templates
        self.jinja_env.globals['now'] = datetime.utcnow
    
    def check_ssl_certificate_exists(self, server, domain_name):
        """
        Проверяет наличие SSL-сертификатов для домена на сервере
        
        Args:
            server: Server model instance
            domain_name: Имя домена для проверки
            
        Returns:
            bool: True если сертификаты существуют и доступны, False в противном случае
        """
        try:
            # Проверяем наличие путей к сертификатам - обратите внимание, что это только проверка наличия, 
            # но не валидности самих сертификатов
            # Исправлен пробел между domain_name и /fullchain.pem
            cert_check_cmd = f"sudo test -f /etc/letsencrypt/live/{domain_name}/fullchain.pem && sudo test -f /etc/letsencrypt/live/{domain_name}/privkey.pem && echo 'SSL_EXISTS' || echo 'SSL_NOT_FOUND'"
            result, _ = ServerManager.execute_command(server, cert_check_cmd)
            
            if "SSL_EXISTS" in result:
                logger.info(f"SSL certificates found for domain {domain_name}")
                return True
            else:
                logger.warning(f"SSL certificates not found for domain {domain_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking SSL certificates for {domain_name}: {str(e)}")
            return False
    
    def generate_nginx_config(self, server):
        """
        Generate Nginx configuration for a server based on its domain groups.
        
        Args:
            server: Server model instance
            
        Returns:
            tuple: (main_config, site_configs) where:
                - main_config is the main nginx.conf content
                - site_configs is a dict mapping domain names to their site configurations
        """
        try:
            # Load templates
            main_template = self.jinja_env.get_template('nginx.conf.j2')
            site_template = self.jinja_env.get_template('site.conf.j2')
            
            # Get domains for the server using DomainManager
            domains = DomainManager.get_domains_by_server(server.id)
            
            # Проверяем, есть ли домены, и логируем для отладки
            if not domains:
                logger.warning(f"No domains found for server {server.id} ({server.name})")
                
                # Для дополнительной диагностики: проверим, есть ли группы доменов
                domain_groups = DomainGroup.query.filter_by(server_id=server.id).all()
                if not domain_groups:
                    logger.warning(f"No domain groups found for server {server.id}")
                else:
                    logger.info(f"Found {len(domain_groups)} domain groups for server {server.id}")
                    for group in domain_groups:
                        domain_count = group.domains.count()
                        logger.info(f"Group {group.id} ({group.name}) has {domain_count} domains")
            else:
                logger.info(f"Found {len(domains)} domains for server {server.id}")
            
            # Generate main Nginx config
            main_config = main_template.render(
                server_name=server.name,
                domains=domains
            )
            
            # Generate site configs for each domain
            site_configs = {}
            for domain in domains:
                # Проверяем наличие SSL сертификатов для доменов с включенным SSL
                ssl_available = False
                if domain.ssl_enabled:
                    ssl_available = self.check_ssl_certificate_exists(server, domain.name)
                
                site_config = site_template.render(
                    domain=domain.name,
                    target_ip=domain.target_ip,
                    target_port=domain.target_port,
                    ssl_enabled=domain.ssl_enabled,
                    ssl_available=ssl_available
                )
                site_configs[domain.name] = site_config
            
            return main_config, site_configs
            
        except Exception as e:
            logger.error(f"Error generating Nginx config for server {server.name}: {str(e)}")
            raise
    
    def deploy_proxy_config(self, server_id):
        """
        Deploy proxy configuration to a server in a background thread.

        Args:
            server_id: ID of the server to deploy to

        Returns:
            bool: True if deployment process was successfully started, False otherwise
        """
        # Инициализируем переменные до блока try для избежания предупреждений
        server = None
        
        try:
            server = Server.query.get(server_id)
            if not server:
                logger.error(f"Server with ID {server_id} not found")
                return False

            # Check server connectivity first
            if not ServerManager.check_connectivity(server):
                logger.error(f"Cannot deploy to server {server.name}: Server is not reachable")
                return False

            # Generate Nginx configurations
            main_config, site_configs = self.generate_nginx_config(server)

            # Проверяем, не пустые ли конфигурации
            if not site_configs:
                logger.error(f"No site configurations found for server {server.name}")
                return False
                
            # Импортируем необходимые модули
            import json
            
            # Сохраняем site_configs в JSON для восстановления в фоновом потоке
            site_configs_json = {}
            for domain_name, config in site_configs.items():
                site_configs_json[domain_name] = config
                
            # Create ProxyConfig record with site configs
            proxy_config = ProxyConfig(
                server_id=server.id,
                config_content=main_config,
                status='pending',
                extra_data=json.dumps(site_configs_json)  # Сохраняем все конфигурации сайтов в БД
            )
            db.session.add(proxy_config)
            db.session.commit()
            
            # Получаем нужные данные для передачи в фоновый поток
            server_name = server.name
            proxy_config_id = proxy_config.id
            templates_path = self.templates_path
            
            # Создаем ссылку на текущее приложение для передачи в поток
            app = current_app._get_current_object()
            
            # Функция для выполнения в фоновом потоке
            def background_deploy(app, server_id, proxy_config_id, templates_path, main_config, site_configs, server_name):
                logger.info(f"Starting background deployment for server {server_name}")
                
                # Импортируем необходимые модули в начале функции
                import json
                
                # Убедимся, что site_configs не потерялось и не пустое
                if not site_configs:
                    logger.error(f"Error: site_configs is empty for server {server_name}")
                else:
                    logger.info(f"Background deployment has {len(site_configs)} site configs for server {server_name}")
                    for domain_name, config in site_configs.items():
                        logger.info(f"Config for {domain_name} is {len(config)} bytes")
                
                try:
                    # Создаем контекст приложения для фонового потока
                    with app.app_context():
                        from models import Server, ServerLog, ProxyConfig, db
                        from modules.server_manager import ServerManager
                        from modules.domain_manager import DomainManager
                        
                        # Восстанавливаем конфигурации из БД (дублирующий механизм)
                        proxy_config = ProxyConfig.query.get(proxy_config_id)
                        if proxy_config and proxy_config.extra_data and not site_configs:
                            logger.info(f"Восстанавливаем конфигурации из БД, т.к. site_configs пустой")
                            try:
                                site_configs = json.loads(proxy_config.extra_data)
                                logger.info(f"Успешно восстановлено {len(site_configs)} конфигураций из БД")
                                for domain_name, config in site_configs.items():
                                    logger.info(f"Восстановлена конфигурация для {domain_name}: {len(config)} байт")
                            except Exception as e:
                                logger.error(f"Ошибка при восстановлении конфигураций из БД: {str(e)}")
                        
                        # Получаем объекты из БД по ID
                        server = Server.query.get(server_id)
                        if not server:
                            logger.error(f"Server with ID {server_id} not found in background thread")
                            return
                            
                        proxy_config = ProxyConfig.query.get(proxy_config_id)
                        if not proxy_config:
                            logger.error(f"ProxyConfig with ID {proxy_config_id} not found in background thread")
                            return

                        # Ensure Nginx is installed
                        try:
                            stdout, stderr = ServerManager.execute_command(
                                server, 
                                "dpkg -l | grep nginx || sudo apt-get update && sudo apt-get install -y nginx"
                            )

                            if "nginx" not in stdout and not "nginx" in stderr:
                                logger.error(f"Failed to verify Nginx installation on server {server.name}")
                                proxy_config.status = 'error'
                                db.session.commit()
                                return
                        except Exception as e:
                            logger.error(f"Error installing Nginx: {str(e)}")
                            proxy_config.status = 'error'
                            db.session.commit()
                            
                            # Create error log entry
                            log = ServerLog(
                                server_id=server.id,
                                action='proxy_deployment',
                                status='error',
                                message=f"Error installing Nginx: {str(e)}"
                            )
                            db.session.add(log)
                            db.session.commit()
                            return

                        try:
                            # Upload main Nginx config
                            ServerManager.upload_string_to_file(
                                server,
                                main_config,
                                "/etc/nginx/nginx.conf"
                            )

                            # Create sites-available and sites-enabled directories if they don't exist
                            ServerManager.execute_command(
                                server,
                                "sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled"
                            )
                            
                            # Удаляем дефолтную конфигурацию nginx, которая может конфликтовать с нашими настройками
                            logger.info(f"Removing default nginx site configuration on server {server.name}")
                            try:
                                ServerManager.execute_command(
                                    server,
                                    "sudo rm -f /etc/nginx/sites-enabled/default"
                                )
                                logger.info(f"Successfully removed default nginx configuration")
                            except Exception as e:
                                logger.warning(f"Warning while removing default configuration: {str(e)}")
                                # Продолжаем, так как файл может уже отсутствовать

                            # Upload site configurations
                            for domain_name, site_config in site_configs.items():
                                sanitized_name = domain_name.replace(".", "_")
                                logger.info(f"Обработка конфигурации для домена {domain_name} (файл: {sanitized_name})")
                                site_path = f"/etc/nginx/sites-available/{sanitized_name}"

                                # Сначала создаем директории, если они не существуют
                                ServerManager.execute_command(
                                    server,
                                    "sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled"
                                )
                                
                                # Проверяем, существует ли уже файл
                                file_check, _ = ServerManager.execute_command(
                                    server,
                                    f"ls -la {site_path} 2>/dev/null || echo 'NOT_FOUND'"
                                )
                                
                                # Upload site config - более надежным способом
                                if "NOT_FOUND" in file_check:
                                    logger.info(f"Файл {site_path} не существует, создаем его напрямую через команду")
                                    # Создаем файл сразу в целевой директории через echo
                                    config_safe = site_config.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
                                    ServerManager.execute_command(
                                        server,
                                        f'echo "{config_safe}" | sudo tee {site_path} > /dev/null && sudo chmod 644 {site_path}'
                                    )
                                else:
                                    logger.info(f"Файл {site_path} существует, обновляем его через upload_string_to_file")
                                    # Обновляем существующий файл
                                    ServerManager.upload_string_to_file(
                                        server,
                                        site_config,
                                        site_path
                                    )
                                
                                # Проверяем, был ли файл создан/обновлен успешно
                                file_exists, _ = ServerManager.execute_command(
                                    server,
                                    f"ls -la {site_path} 2>/dev/null || echo 'NOT_FOUND'"
                                )
                                
                                if "NOT_FOUND" in file_exists:
                                    logger.error(f"Не удалось создать файл {site_path}! Пробуем крайний метод")
                                    # Экстренная мера - пишем напрямую через cat
                                    config_lines = site_config.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`').split('\n')
                                    ServerManager.execute_command(
                                        server,
                                        f'sudo touch {site_path} && sudo chmod 666 {site_path}'
                                    )
                                    for line in config_lines:
                                        if line.strip():
                                            ServerManager.execute_command(
                                                server,
                                                f'echo "{line}" | sudo tee -a {site_path} > /dev/null'
                                            )
                                    ServerManager.execute_command(
                                        server,
                                        f'sudo chmod 644 {site_path}'
                                    )
                                
                                # Create symlink in sites-enabled - с полной проверкой
                                logger.info(f"Создаем символическую ссылку для {sanitized_name}")
                                
                                # Удаляем старую ссылку, если существует
                                ServerManager.execute_command(
                                    server,
                                    f"sudo rm -f /etc/nginx/sites-enabled/{sanitized_name}"
                                )
                                
                                # Создаем новую ссылку
                                symlink_result, symlink_error = ServerManager.execute_command(
                                    server,
                                    f"sudo ln -sf {site_path} /etc/nginx/sites-enabled/{sanitized_name}"
                                )
                                
                                # Проверяем, существует ли файл после создания символической ссылки
                                exists_check, _ = ServerManager.execute_command(
                                    server,
                                    f"ls -la /etc/nginx/sites-enabled/{sanitized_name} 2>/dev/null || echo 'NOT_FOUND'"
                                )
                                
                                if "NOT_FOUND" in exists_check:
                                    logger.warning(f"Ссылка не была создана корректно для {sanitized_name}. Копируем файл напрямую.")
                                    # Копируем файл напрямую, если ссылка не работает
                                    ServerManager.execute_command(
                                        server,
                                        f"sudo cp {site_path} /etc/nginx/sites-enabled/{sanitized_name} && sudo chmod 644 /etc/nginx/sites-enabled/{sanitized_name}"
                                    )

                            # Убедимся, что все каталоги для сертификатов существуют
                            ServerManager.execute_command(
                                server,
                                "sudo mkdir -p /etc/letsencrypt/live/ /etc/ssl/certs/ /etc/ssl/private/"
                            )

                            # Test Nginx configuration
                            stdout, stderr = ServerManager.execute_command(
                                server,
                                "sudo nginx -t"
                            )

                            if "successful" not in stdout and "successful" not in stderr:
                                # Проверяем, является ли ошибка конфликтом default_server
                                if "duplicate default server for 0.0.0.0:80" in stderr:
                                    logger.warning(f"Detected duplicate default server conflict, trying to fix it")

                                    # Пытаемся удалить существующие default_server параметры
                                    ServerManager.execute_command(
                                        server,
                                        "sudo sed -i 's/default_server//g' /etc/nginx/sites-enabled/*"
                                    )

                                    # Повторно проверяем конфигурацию
                                    stdout, stderr = ServerManager.execute_command(
                                        server,
                                        "sudo nginx -t"
                                    )

                                    if "successful" not in stdout and "successful" not in stderr:
                                        logger.error(f"Still failing after fixing default_server conflict: {stderr}")
                                        proxy_config.status = 'error'
                                        db.session.commit()

                                        # Create log entry
                                        log = ServerLog(
                                            server_id=server.id,
                                            action='proxy_deployment',
                                            status='error',
                                            message=f"Nginx configuration test failed after trying to fix: {stderr}"
                                        )
                                        db.session.add(log)
                                        db.session.commit()
                                        return
                                    else:
                                        logger.info("Successfully fixed default_server conflict")
                                else:
                                    logger.error(f"Nginx configuration test failed on server {server.name}: {stderr}")
                                    proxy_config.status = 'error'
                                    db.session.commit()

                                    # Create log entry
                                    log = ServerLog(
                                        server_id=server.id,
                                        action='proxy_deployment',
                                        status='error',
                                        message=f"Nginx configuration test failed: {stderr}"
                                    )
                                    db.session.add(log)
                                    db.session.commit()
                                    return

                            # Проверяем наличие SSL сертификатов для каждого домена и обновляем конфигурацию
                            domains = DomainManager.get_domains_by_server(server.id)
                            ssl_domains = [d for d in domains if d.ssl_enabled]

                            # Если есть домены с включенным SSL, проверяем наличие сертификатов
                            if ssl_domains:
                                logger.info(f"Checking SSL certificates for {len(ssl_domains)} domains")
                                for domain in ssl_domains:
                                    domain_safe = domain.name.replace(".", "_")
                                    site_path = f"/etc/nginx/sites-available/{domain_safe}"

                                    # Проверяем наличие сертификатов
                                    cert_check_cmd = f"sudo ls -la /etc/letsencrypt/live/{domain.name}/fullchain.pem 2>/dev/null || echo 'Not found'"
                                    cert_result, _ = ServerManager.execute_command(server, cert_check_cmd)

                                    if "Not found" not in cert_result:
                                        # Сертификаты существуют, заменяем самоподписанные на настоящие
                                        logger.info(f"Found SSL certificates for {domain.name}, updating configuration")

                                        # Команда для замены самоподписанных сертификатов на настоящие в конфигурации
                                        update_cmd = f"""sudo sed -i 's|ssl_certificate .*snakeoil.pem;|ssl_certificate /etc/letsencrypt/live/{domain.name}/fullchain.pem;|' {site_path} && \
                                                        sudo sed -i 's|ssl_certificate_key .*snakeoil.key;|ssl_certificate_key /etc/letsencrypt/live/{domain.name}/privkey.pem;|' {site_path} && \
                                                        sudo sed -i 's|# include /etc/letsencrypt/options-ssl-nginx.conf;|include /etc/letsencrypt/options-ssl-nginx.conf;|' {site_path} && \
                                                        sudo sed -i 's|# ssl_dhparam|ssl_dhparam|' {site_path}"""

                                        try:
                                            ServerManager.execute_command(server, update_cmd)
                                            logger.info(f"SSL configuration updated for {domain.name}")
                                        except Exception as e:
                                            logger.warning(f"Could not update SSL configuration for {domain.name}: {str(e)}")

                            # Reload Nginx to apply changes
                            stdout, stderr = ServerManager.execute_command(
                                server,
                                "sudo systemctl reload nginx || sudo systemctl restart nginx"
                            )

                            # Update ProxyConfig status
                            proxy_config.status = 'deployed'
                            db.session.commit()

                            # Create log entry
                            log = ServerLog(
                                server_id=server.id,
                                action='proxy_deployment',
                                status='success',
                                message="Proxy configuration deployed successfully"
                            )
                            db.session.add(log)
                            db.session.commit()

                            logger.info(f"Successfully deployed proxy configuration to server {server.name}")
                            
                        except Exception as e:
                            logger.error(f"Error in proxy deployment process: {str(e)}")
                            
                            # Update proxy config status
                            proxy_config.status = 'error'
                            db.session.commit()
                            
                            # Create log entry
                            log = ServerLog(
                                server_id=server.id,
                                action='proxy_deployment',
                                status='error',
                                message=f"Deployment error: {str(e)}"
                            )
                            db.session.add(log)
                            db.session.commit()
                    
                except Exception as e:
                    logger.error(f"Critical error in background deployment thread: {str(e)}")
                    # Attempt to update database with error if possible
                    try:
                        with app.app_context():
                            from models import ProxyConfig, ServerLog, db
                            
                            # Try to get the proxy config by ID
                            proxy_config = ProxyConfig.query.get(proxy_config_id)
                            if proxy_config:
                                proxy_config.status = 'error'
                                
                                # Create error log
                                log = ServerLog(
                                    server_id=server_id,
                                    action='proxy_deployment',
                                    status='error',
                                    message=f"Critical background thread error: {str(e)}"
                                )
                                db.session.add(log)
                                db.session.commit()
                    except Exception as inner_e:
                        logger.error(f"Failed to log error in database: {str(inner_e)}")
            
            # Проверяем, не пустые ли конфигурации перед передачей в фоновый поток
            if not site_configs:
                logger.error(f"ERROR: site_configs is empty for server {server_name}")
                proxy_config.status = 'error'
                db.session.commit()
                # Импортируем ServerLog здесь
                from models import ServerLog
                log = ServerLog(
                    server_id=server_id,
                    action='proxy_deployment',
                    status='error',
                    message=f"No site configurations found for server {server_name}"
                )
                db.session.add(log)
                db.session.commit()
                return False
                
            # Логируем содержимое конфигураций перед запуском потока
            logger.info(f"Starting background deployment for server {server_name} with {len(site_configs)} site configs")
            for domain_name, config in site_configs.items():
                logger.info(f"Main thread: Config for {domain_name} is {len(config)} bytes")
                
            # Сохраняем конфигурации в БД перед запуском фонового потока
            if site_configs:
                try:
                    import json
                    # Получаем объект конфигурации
                    proxy_config = ProxyConfig.query.get(proxy_config_id)
                    if proxy_config:
                        proxy_config.extra_data = json.dumps(site_configs)
                        db.session.commit()
                        logger.info(f"Сохранено {len(site_configs)} конфигураций сайтов в БД для сервера {server_name}")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении конфигураций в БД: {str(e)}")
            
            # Создаем глубокую копию конфигураций для передачи в поток
            site_configs_copy = site_configs.copy()
            
            # Запускаем фоновый поток с копией конфигураций
            background_thread = Thread(target=background_deploy, args=(app, server_id, proxy_config_id, templates_path, main_config, site_configs_copy, server_name))
            background_thread.daemon = True
            background_thread.start()
            
            # Возвращаем True, так как процесс успешно запущен в фоне
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error starting deployment process for server {server_id}: {str(e)}")
            
            # Create log entry if server exists
            try:
                # Импортируем модель Server заранее, чтобы избежать ошибки
                from models import Server
                
                # Получаем server снова, если он не определен или был очищен
                server_obj = None
                if 'server' in locals() and server:
                    server_obj = server
                else:
                    # Здесь модель Server уже доступна
                    server_obj = Server.query.get(server_id)
                    
                if server_obj:
                    # Импортировать ServerLog внутри блока исключения
                    from models import ServerLog
                    log = ServerLog(
                        server_id=server_obj.id,
                        action='proxy_deployment',
                        status='error',
                        message=f"Error starting deployment: {str(e)}"
                    )
                    db.session.add(log)
                    db.session.commit()
            except Exception as inner_e:
                logger.error(f"Failed to create error log: {str(inner_e)}")
                
            return False
