import logging
import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required
from models import Server, Domain, ProxyConfig, ServerLog, db
from modules.proxy_manager import ProxyManager
from modules.deployment import DeploymentManager

bp = Blueprint('proxy', __name__, url_prefix='/proxy')
logger = logging.getLogger(__name__)

@bp.route('/deploy/<int:server_id>', methods=['GET'])
@login_required
def deploy(server_id):
    """Deploy proxy configuration to a server."""
    server = Server.query.get_or_404(server_id)
    
    # Check if server is active
    if server.status != 'active':
        # Try to check connectivity first
        from modules.server_manager import ServerManager
        if not ServerManager.check_connectivity(server):
            flash(f'Cannot deploy to server {server.name} because it is not reachable', 'danger')
            return redirect(url_for('servers.index'))
    
    # Create proxy manager
    nginx_templates_path = os.path.join(current_app.root_path, 'templates', 'nginx')
    proxy_manager = ProxyManager(nginx_templates_path)
    
    # Deploy configuration
    try:
        success = proxy_manager.deploy_proxy_config(server_id)
        
        if success:
            flash(f'Proxy configuration successfully deployed to server {server.name}', 'success')
        else:
            flash(f'Failed to deploy proxy configuration to server {server.name}', 'danger')
    except Exception as e:
        logger.exception("Error deploying proxy configuration")
        flash(f'Error deploying proxy configuration: {str(e)}', 'danger')
    
    # Redirect back to referring page or servers index
    referrer = request.referrer
    if referrer and ('/servers/' in referrer or '/domain-groups/' in referrer):
        return redirect(referrer)
    else:
        return redirect(url_for('servers.index'))

@bp.route('/setup-ssl/<int:server_id>', methods=['GET', 'POST'])
@login_required
def setup_ssl(server_id):
    """Set up SSL certificates for domains on a server."""
    server = Server.query.get_or_404(server_id)
    
    # Получаем опциональный параметр domain_id из URL
    domain_id = request.args.get('domain_id', None)
    selected_domain = None
    
    if domain_id:
        try:
            selected_domain = Domain.query.get_or_404(int(domain_id))
            # Убеждаемся, что домен принадлежит запрошенному серверу через группу
            domain_on_server = False
            for group in selected_domain.groups:
                if group.server_id == server_id:
                    domain_on_server = True
                    break
                    
            if not domain_on_server:
                flash('Домен не связан с указанным сервером через группу доменов', 'danger')
                return redirect(url_for('domains.index'))
        except Exception as e:
            logger.error(f"Ошибка при получении информации о домене: {str(e)}")
            flash(f'Ошибка при получении информации о домене: {str(e)}', 'danger')
            return redirect(url_for('servers.server_detail', server_id=server_id))
    
    # Get SSL-enabled domains for this server
    from modules.domain_manager import DomainManager
    domains = DomainManager.get_domains_by_server(server_id)
    
    # Фильтруем домены в зависимости от параметров
    if selected_domain:
        # Если выбран конкретный домен, используем только его
        ssl_domains = [selected_domain] if selected_domain.ssl_enabled else []
    else:
        # Иначе используем все домены с включенным SSL
        ssl_domains = [d for d in domains if d.ssl_enabled]
    
    # Get SSL setup logs
    logs = ServerLog.query.filter_by(
        server_id=server.id, 
        action='ssl_setup'
    ).order_by(ServerLog.created_at.desc()).limit(10).all()
    
    # Get admin email from config
    admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
    
    # Handle GET request - show the setup page
    if request.method == 'GET':
        if not ssl_domains:
            if selected_domain:
                flash(f'Домен {selected_domain.name} не имеет включенного SSL', 'warning')
            else:
                flash(f'No SSL-enabled domains found for server {server.name}', 'warning')
            
        return render_template(
            'proxy/ssl_setup.html',
            server=server,
            ssl_domains=ssl_domains,
            logs=logs,
            admin_email=admin_email,
            selected_domain=selected_domain
        )
    
    # Handle POST request - perform SSL setup
    if not ssl_domains:
        if selected_domain:
            flash(f'Домен {selected_domain.name} не имеет включенного SSL', 'warning')
        else:
            flash(f'No SSL-enabled domains found for server {server.name}', 'warning')
        return redirect(url_for('proxy.setup_ssl', server_id=server_id, domain_id=domain_id))
    
    # Get email from form
    email = request.form.get('admin_email', admin_email)
    
    # Update config temporarily
    current_app.config['ADMIN_EMAIL'] = email
    
    # Set up SSL using Certbot
    try:
        # Используем соответствующий метод в зависимости от того, один домен или несколько
        if selected_domain:
            # Для одного домена используем специальный метод
            success = DeploymentManager.setup_ssl_certbot_domain(server, selected_domain)
        else:
            # Для нескольких доменов используем общий метод
            success = DeploymentManager.setup_ssl_certbot(server, ssl_domains)
        
        if success:
            if selected_domain:
                flash(f'Процесс выпуска SSL-сертификата для {selected_domain.name} запущен. Это может занять несколько минут.', 'success')
            else:
                flash(f'SSL certificates successfully set up for {len(ssl_domains)} domains on server {server.name}', 'success')
        else:
            if selected_domain:
                flash(f'Не удалось запустить процесс выпуска SSL-сертификата для {selected_domain.name}', 'danger')
            else:
                flash(f'Failed to set up SSL certificates on server {server.name}', 'danger')
    except Exception as e:
        logger.exception("Error setting up SSL certificates")
        flash(f'Error setting up SSL certificates: {str(e)}', 'danger')
    
    # Перенаправление в зависимости от контекста
    if selected_domain:
        return redirect(url_for('domains.index'))
    else:
        return redirect(url_for('proxy.setup_ssl', server_id=server_id))

@bp.route('/install-nginx/<int:server_id>', methods=['GET', 'POST'])
@login_required
def install_nginx(server_id):
    """Install Nginx on a server."""
    server = Server.query.get_or_404(server_id)
    
    # Get installation logs
    logs = ServerLog.query.filter_by(
        server_id=server.id, 
        action='install_nginx'
    ).order_by(ServerLog.created_at.desc()).limit(10).all()
    
    # Get the latest successful installation log, if any
    latest_log = ServerLog.query.filter_by(
        server_id=server.id,
        action='install_nginx',
        status='success'
    ).order_by(ServerLog.created_at.desc()).first()
    
    # Check server connectivity status
    from modules.server_manager import ServerManager
    server_status = 'active' if ServerManager.check_connectivity(server) else 'error'
    
    # Handle GET request - show the installation page
    if request.method == 'GET':
        return render_template(
            'proxy/install_nginx.html',
            server=server,
            logs=logs,
            latest_log=latest_log,
            server_status=server_status
        )
    
    # Handle POST request - install Nginx
    if server_status != 'active':
        flash(f'Cannot install Nginx: Server {server.name} is not reachable', 'danger')
        return redirect(url_for('proxy.install_nginx', server_id=server_id))
    
    # Create log entry for installation attempt
    log = ServerLog(
        server_id=server.id,
        action='install_nginx',
        status='pending',
        message=f'Installing Nginx on server {server.name}'
    )
    db.session.add(log)
    db.session.commit()
    
    # Install Nginx
    try:
        success = DeploymentManager.deploy_nginx(server)
        
        if success:
            # Update log entry
            log.status = 'success'
            log.message = f'Nginx successfully installed on server {server.name}'
            db.session.commit()
            
            # Do not flash the message as it will be shown on the page
            # flash(f'Nginx successfully installed on server {server.name}', 'success')
        else:
            # Update log entry
            log.status = 'error'
            log.message = f'Failed to install Nginx on server {server.name}'
            db.session.commit()
            
            flash(f'Failed to install Nginx on server {server.name}', 'danger')
    except Exception as e:
        logger.exception("Error installing Nginx")
        
        # Update log entry
        log.status = 'error'
        log.message = f'Error installing Nginx: {str(e)}'
        db.session.commit()
        
        flash(f'Error installing Nginx: {str(e)}', 'danger')
    
    # Refresh the page to show the new state
    return redirect(url_for('proxy.install_nginx', server_id=server_id))

@bp.route('/configs/<int:server_id>', methods=['GET'])
@login_required
def view_configs(server_id):
    """View proxy configurations for a server."""
    server = Server.query.get_or_404(server_id)
    
    # Get configurations
    configs = ProxyConfig.query.filter_by(server_id=server_id).order_by(ProxyConfig.created_at.desc()).all()
    
    # Generate preview of current config
    nginx_templates_path = os.path.join(current_app.root_path, 'templates', 'nginx')
    proxy_manager = ProxyManager(nginx_templates_path)
    
    try:
        main_config, site_configs = proxy_manager.generate_nginx_config(server)
        config_preview = {
            'main_config': main_config,
            'site_configs': site_configs
        }
    except Exception as e:
        logger.exception("Error generating config preview")
        config_preview = None
        flash(f'Error generating configuration preview: {str(e)}', 'warning')
    
    return render_template('proxy/configs.html', 
                          server=server, 
                          configs=configs,
                          config_preview=config_preview)
