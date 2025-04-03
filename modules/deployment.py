@classmethod
def setup_ssl_certbot(cls, server, domains):
    """
    Set up SSL certificates using Certbot for the specified domains.
    Выполняет в фоновом режиме для избежания таймаутов.
    
    Args:
        server: Server model instance
        domains: List of Domain model instances
        
    Returns:
        bool: True if background task started successfully, False otherwise
    """
    from threading import Thread
    from flask import current_app
    import time
    
    # Check connectivity first
    if not ServerManager.check_connectivity(server):
        logger.error(f"Cannot set up SSL for server {server.name}: Server is not reachable")
        return False
        
    # Функция для выполнения в фоновом потоке
    def background_ssl_setup():
        try:
            # Создаем контекст приложения для фонового потока
            with current_app.app_context():
                # Create log entry
                log = ServerLog(
                    server_id=server.id,
                    action='ssl_setup',
                    status='pending',
                    message=f"Setting up SSL for {len(domains)} domains"
                )
                db.session.add(log)
                db.session.commit()
                
                # Install Certbot (long-running operation)
                logger.info(f"Installing Certbot on server {server.name}")
                try:
                    ServerManager.execute_command(
                        server,
                        "sudo apt-get update -q", 
                        long_running=True
                    )
                    
                    ServerManager.execute_command(
                        server,
                        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx",
                        long_running=True
                    )
                except Exception as e:
                    logger.warning(f"Certbot installation warning on {server.name}: {str(e)}")
                    # Continue anyway, might be just a transient error
                
                # Get list of domains that need SSL
                ssl_domains = [d for d in domains if d.ssl_enabled]
                
                if not ssl_domains:
                    log.status = 'success'
                    log.message = "No domains with SSL enabled found"
                    db.session.commit()
                    return
                
                # Get admin email from config or use a default
                admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
                
                # Generate certification command
                domain_args = " ".join([f"-d {d.name}" for d in ssl_domains])
                cert_command = f"sudo certbot --nginx --expand --non-interactive --agree-tos --email {admin_email} {domain_args}"
                
                # Run certification command (can take a long time)
                logger.info(f"Obtaining SSL certificates for {len(ssl_domains)} domains on server {server.name}")
                stdout, stderr = ServerManager.execute_command(server, cert_command, long_running=True)
                
                if "Congratulations" in stdout or "Successfully received certificate" in stdout:
                    # Certbot автоматически добавляет редирект с HTTP на HTTPS, даже если наш шаблон этого не делает
                    # Удалим редирект для каждого домена
                    for domain in ssl_domains:
                        domain_safe = domain.name.replace(".", "_")
                        config_path = f"/etc/nginx/sites-available/{domain_safe}"
                        
                        # Команда удаляет редирект - ищет return 301 и заменяет весь блок location на правильный
                        cmd = f'''sudo grep -l "return 301" {config_path} && sudo sed -i '/location \\/ {{/,/}}/c\\    location / {{\\n        proxy_pass http:\\/\\/{domain.target_ip}:{domain.target_port};\\n        proxy_set_header Host $host;\\n        proxy_set_header X-Real-IP $remote_addr;\\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\\n        proxy_set_header X-Forwarded-Proto $scheme;\\n        proxy_http_version 1.1;\\n        proxy_set_header Upgrade $http_upgrade;\\n        proxy_set_header Connection "upgrade";\\n        proxy_connect_timeout 60s;\\n        proxy_send_timeout 60s;\\n        proxy_read_timeout 60s;\\n    }}' {config_path} || echo "No redirect found"'''
                        
                        try:
                            ServerManager.execute_command(server, cmd)
                            logger.info(f"Removed automatic HTTPS redirect for domain {domain.name}")
                        except Exception as e:
                            logger.warning(f"Could not remove HTTPS redirect for {domain.name}: {str(e)}")
                    
                    # Перезагрузим nginx чтобы применить изменения
                    try:
                        ServerManager.execute_command(server, "sudo systemctl reload nginx")
                        logger.info(f"Reloaded Nginx after removing HTTPS redirects")
                    except Exception as e:
                        logger.warning(f"Could not reload Nginx: {str(e)}")
                    
                    # Обновим статус домена в базе данных
                    for domain in ssl_domains:
                        # Добавим проверку наличия сертификата, чтобы убедиться, что он установлен
                        cert_check_cmd = f"sudo ls -la /etc/letsencrypt/live/{domain.name}/fullchain.pem || echo 'Not found'"
                        cert_result, _ = ServerManager.execute_command(server, cert_check_cmd)
                        
                        if "Not found" not in cert_result:
                            # Сертификат существует - обновляем статус домена
                            domain_model = Domain.query.get(domain.id)
                            if domain_model:
                                # Установленный флаг для отображения в интерфейсе
                                domain_model.ssl_status = "active"
                                domain_model.has_ssl = True
                                logger.info(f"Updated SSL status for domain {domain.name} to 'active'")
                        else:
                            logger.warning(f"SSL certificate not found for domain {domain.name}")
                    
                    # Сохраним изменения в БД
                    db.session.commit()
                    
                    # Update log entry
                    log.status = 'success'
                    log.message = f"SSL certificates obtained successfully for {len(ssl_domains)} domains"
                    db.session.commit()
                    
                    logger.info(f"Successfully set up SSL certificates on server {server.name}")
                else:
                    # Update log entry
                    log.status = 'error'
                    log.message = f"SSL certificate acquisition failed: {stdout}\n{stderr}"
                    db.session.commit()
                    
                    logger.error(f"Failed to set up SSL certificates on server {server.name}: {stderr}")
                    
        except Exception as e:
            # Create error log entry for SSL setup
            with current_app.app_context():
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
    
    # Обновим статусы доменов перед запуском процесса
    try:
        for domain in domains:
            if domain.ssl_enabled:
                domain.ssl_status = 'pending'
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to update domain status: {str(e)}")
    
    # Запускаем фоновый поток
    background_thread = Thread(target=background_ssl_setup)
    background_thread.daemon = True
    background_thread.start()
    
    # Возвращаем True, так как процесс успешно запущен в фоне
    return True