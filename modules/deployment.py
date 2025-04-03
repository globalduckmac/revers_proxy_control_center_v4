import logging
import os
import re
import time
from threading import Thread
from flask import current_app
from datetime import datetime
import json
from models import Server, Domain, ServerLog, db, SystemSetting
from modules.server_manager import ServerManager

logger = logging.getLogger(__name__)

class DeploymentManager:
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
                        logger.error(f"Error installing Certbot on server {server.name}: {str(e)}")
                        log.status = 'error'
                        log.message = f"Error installing Certbot: {str(e)}"
                        db.session.commit()
                        return
                    
                    # Generate certificates for selected domains
                    logger.info(f"Generating SSL certificates for {len(domains)} domains on server {server.name}")
                    
                    domain_list = []
                    for domain in domains:
                        domain_list.append(domain.name)
                        # Include www subdomain if configured
                        if domain.include_www:
                            domain_list.append(f"www.{domain.name}")
                    
                    # Format domain list for certbot command
                    domain_args = " ".join([f"-d {d}" for d in domain_list])
                    
                    # Check if we should use staging environment for testing
                    staging_setting = SystemSetting.query.filter_by(key='certbot_staging').first()
                    staging_arg = "--staging" if staging_setting and staging_setting.value == 'true' else ""
                    
                    # Create combined command for all domains
                    logger.debug(f"Certbot domain arguments: {domain_args}")
                    try:
                        # We need to stop nginx before running certbot
                        ServerManager.execute_command(
                            server,
                            "sudo systemctl stop nginx",
                            long_running=True
                        )
                        
                        # Run certbot command
                        certbot_command = f"sudo certbot certonly --standalone {staging_arg} --non-interactive --agree-tos --email admin@example.com {domain_args}"
                        logger.info(f"Running certbot command: {certbot_command}")
                        
                        result = ServerManager.execute_command(
                            server,
                            certbot_command,
                            long_running=True
                        )
                        
                        # Start nginx again
                        ServerManager.execute_command(
                            server,
                            "sudo systemctl start nginx",
                            long_running=True
                        )
                        
                        # Check if certificates were created successfully
                        success = True
                        for domain in domains:
                            cert_path = f"/etc/letsencrypt/live/{domain.name}/fullchain.pem"
                            check_result = ServerManager.execute_command(
                                server,
                                f"sudo [ -f {cert_path} ] && echo 'Certificate exists' || echo 'Certificate not found'"
                            )
                            if "Certificate not found" in check_result:
                                logger.error(f"SSL certificate for {domain.name} was not created")
                                success = False
                            else:
                                # Update domain SSL status
                                domain.has_ssl = True
                                db.session.commit()
                                logger.info(f"SSL certificate for {domain.name} was created successfully")
                        
                        if success:
                            log.status = 'success'
                            log.message = f"SSL certificates created successfully for {len(domains)} domains"
                        else:
                            log.status = 'error'
                            log.message = f"Some SSL certificates were not created correctly. Check server logs."
                            
                    except Exception as e:
                        logger.error(f"Error generating SSL certificates: {str(e)}")
                        log.status = 'error'
                        log.message = f"Error generating SSL certificates: {str(e)}"
                    
                    # Commit updates to database
                    db.session.commit()
                    
            except Exception as e:
                logger.error(f"Error in background SSL setup: {str(e)}")
                # Try to update log if possible
                try:
                    with current_app.app_context():
                        log = ServerLog.query.filter_by(
                            server_id=server.id,
                            action='ssl_setup',
                            status='pending'
                        ).order_by(ServerLog.created_at.desc()).first()
                        
                        if log:
                            log.status = 'error'
                            log.message = f"Background error: {str(e)}"
                            db.session.commit()
                except Exception as inner_e:
                    logger.error(f"Failed to update log entry: {str(inner_e)}")
        
        # Start the background task
        logger.info(f"Starting background SSL setup for server {server.name}")
        thread = Thread(target=background_ssl_setup)
        thread.daemon = True
        thread.start()
        
        return True

    @classmethod
    def setup_ssl_certbot_domain(cls, server, domain):
        """
        Set up SSL certificate using Certbot for a single domain.
        Wrapper around setup_ssl_certbot for single domain operation.
        
        Args:
            server: Server model instance
            domain: Domain model instance
            
        Returns:
            bool: True if background task started successfully, False otherwise
        """
        return cls.setup_ssl_certbot(server, [domain])