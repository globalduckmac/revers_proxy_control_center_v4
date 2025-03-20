import os
import logging
import tempfile
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from models import Server, Domain, DomainGroup, ProxyConfig, ServerLog, db
from modules.server_manager import ServerManager

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
            
            # Get all domain groups for the server
            domain_groups = DomainGroup.query.filter_by(server_id=server.id).all()
            
            # Collect all domains from these groups
            all_domains = []
            for group in domain_groups:
                all_domains.extend(group.domains.all())
            
            # Remove duplicates
            domains = list({domain.id: domain for domain in all_domains}.values())
            
            # Generate main Nginx config
            main_config = main_template.render(
                server_name=server.name,
                domains=domains
            )
            
            # Generate site configs for each domain
            site_configs = {}
            for domain in domains:
                site_config = site_template.render(
                    domain=domain.name,
                    target_ip=domain.target_ip,
                    target_port=domain.target_port,
                    ssl_enabled=domain.ssl_enabled
                )
                site_configs[domain.name] = site_config
            
            return main_config, site_configs
            
        except Exception as e:
            logger.error(f"Error generating Nginx config for server {server.name}: {str(e)}")
            raise
    
    def deploy_proxy_config(self, server_id):
        """
        Deploy proxy configuration to a server.
        
        Args:
            server_id: ID of the server to deploy to
            
        Returns:
            bool: True if deployment was successful, False otherwise
        """
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
            
            # Create ProxyConfig record
            proxy_config = ProxyConfig(
                server_id=server.id,
                config_content=main_config,
                status='pending'
            )
            db.session.add(proxy_config)
            db.session.commit()
            
            # Ensure Nginx is installed
            stdout, stderr = ServerManager.execute_command(
                server, 
                "dpkg -l | grep nginx || sudo apt-get update && sudo apt-get install -y nginx"
            )
            
            if "nginx" not in stdout and not "nginx" in stderr:
                logger.error(f"Failed to verify Nginx installation on server {server.name}")
                proxy_config.status = 'error'
                db.session.commit()
                return False
            
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
            
            # Upload site configurations
            for domain_name, site_config in site_configs.items():
                sanitized_name = domain_name.replace(".", "_")
                site_path = f"/etc/nginx/sites-available/{sanitized_name}"
                
                # Upload site config
                ServerManager.upload_string_to_file(
                    server,
                    site_config,
                    site_path
                )
                
                # Create symlink in sites-enabled
                ServerManager.execute_command(
                    server,
                    f"sudo ln -sf {site_path} /etc/nginx/sites-enabled/{sanitized_name}"
                )
            
            # Test Nginx configuration
            stdout, stderr = ServerManager.execute_command(
                server,
                "sudo nginx -t"
            )
            
            if "successful" not in stdout and "successful" not in stderr:
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
                return False
            
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
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deploying proxy configuration to server {server_id}: {str(e)}")
            
            # Create log entry if server exists
            try:
                if server:
                    log = ServerLog(
                        server_id=server.id,
                        action='proxy_deployment',
                        status='error',
                        message=f"Deployment error: {str(e)}"
                    )
                    db.session.add(log)
                    db.session.commit()
            except:
                pass
                
            return False
