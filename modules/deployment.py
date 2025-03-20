import logging
import tempfile
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from models import Server, Domain, DomainGroup, ProxyConfig, ServerLog, db
from modules.server_manager import ServerManager

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
            domains: List of Domain model instances
            
        Returns:
            bool: True if successful, False otherwise
        """
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
                return True
            
            # Get admin email from config or use a default
            from flask import current_app
            admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
            
            # Generate certification command
            domain_args = " ".join([f"-d {d.name}" for d in ssl_domains])
            cert_command = f"sudo certbot --nginx --non-interactive --agree-tos --email {admin_email} {domain_args}"
            
            # Run certification command (can take a long time)
            logger.info(f"Obtaining SSL certificates for {len(ssl_domains)} domains on server {server.name}")
            stdout, stderr = ServerManager.execute_command(server, cert_command, long_running=True)
            
            if "Congratulations" in stdout or "Successfully received certificate" in stdout:
                # Update log entry
                log.status = 'success'
                log.message = f"SSL certificates obtained successfully for {len(ssl_domains)} domains"
                db.session.commit()
                
                logger.info(f"Successfully set up SSL certificates on server {server.name}")
                return True
            else:
                # Update log entry
                log.status = 'error'
                log.message = f"SSL certificate acquisition failed: {stdout}\n{stderr}"
                db.session.commit()
                
                logger.error(f"Failed to set up SSL certificates on server {server.name}: {stderr}")
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
                
            logger.error(f"Error setting up SSL on server {server.name}: {str(e)}")
            return False
