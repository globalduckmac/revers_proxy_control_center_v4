import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from models import Server, ServerLog, ServerGroup, db
from modules.server_manager import ServerManager
from modules.domain_manager import DomainManager
from sqlalchemy import func

bp = Blueprint('servers', __name__, url_prefix='/servers')
logger = logging.getLogger(__name__)

@bp.route('/')
@login_required
def index():
    """Show list of servers."""
    group_id = request.args.get('group_id', type=int)
    
    # Получаем все группы серверов
    groups = ServerGroup.query.order_by(ServerGroup.name).all()
    
    # Фильтрация серверов по группе, если указана
    if group_id:
        group = ServerGroup.query.get_or_404(group_id)
        servers = group.servers.all()
    else:
        servers = Server.query.all()
    
    # Подсчитаем домены для каждого сервера
    server_domains = {}
    for server in servers:
        domains = DomainManager.get_domains_by_server(server.id)
        server_domains[server.id] = len(domains)
    
    # Получаем группы для каждого сервера
    server_groups = {}
    for server in servers:
        server_groups[server.id] = [group.name for group in server.groups]
    
    return render_template(
        'servers/index.html', 
        servers=servers, 
        server_domains=server_domains,
        groups=groups,
        current_group_id=group_id,
        server_groups=server_groups
    )

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Handle server creation."""
    # Получаем все группы серверов для выпадающего списка
    groups = ServerGroup.query.order_by(ServerGroup.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        ssh_user = request.form.get('ssh_user')
        ssh_port = request.form.get('ssh_port', 22, type=int)
        auth_method = request.form.get('auth_method')
        ssh_key = request.form.get('ssh_key') if auth_method == 'key' else None
        ssh_password = request.form.get('ssh_password') if auth_method == 'password' else None
        verify_connection = 'verify_connection' in request.form
        
        # Получаем выбранные группы (может быть несколько)
        selected_group_ids = request.form.getlist('server_groups')
        
        # Validate required fields
        if not name or not ip_address or not ssh_user:
            flash('Все обязательные поля должны быть заполнены', 'danger')
            return render_template('servers/create.html', groups=groups)
        
        # Validate authentication method
        if auth_method == 'key' and not ssh_key and verify_connection:
            flash('SSH ключ обязателен при использовании аутентификации по ключу', 'danger')
            return render_template('servers/create.html', groups=groups)
        
        if auth_method == 'password' and not ssh_password and verify_connection:
            flash('SSH пароль обязателен при использовании аутентификации по паролю', 'danger')
            return render_template('servers/create.html', groups=groups)
        
        # Create server
        server = Server(
            name=name,
            ip_address=ip_address,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            ssh_key=ssh_key,
            ssh_password=ssh_password,
            status='pending'
        )
        
        db.session.add(server)
        
        # Добавляем сервер в выбранные группы
        if selected_group_ids:
            selected_groups = ServerGroup.query.filter(ServerGroup.id.in_(selected_group_ids)).all()
            for group in selected_groups:
                server.groups.append(group)
        
        db.session.commit()
        
        # Check connectivity if requested
        if verify_connection:
            if ServerManager.check_connectivity(server):
                flash(f'Сервер {name} успешно добавлен и подключение проверено', 'success')
            else:
                flash(f'Сервер {name} добавлен, но проверка подключения не удалась', 'warning')
        else:
            flash(f'Сервер {name} успешно добавлен', 'success')
        
        return redirect(url_for('servers.index'))
    
    return render_template('servers/create.html', groups=groups)

@bp.route('/<int:server_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(server_id):
    """Handle server editing."""
    server = Server.query.get_or_404(server_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        ssh_user = request.form.get('ssh_user')
        ssh_port = request.form.get('ssh_port', 22, type=int)
        auth_method = request.form.get('auth_method')
        ssh_key = request.form.get('ssh_key') if auth_method == 'key' else None
        ssh_password = request.form.get('ssh_password') if auth_method == 'password' else None
        verify_connection = 'verify_connection' in request.form
        
        # Update server information
        server.name = name
        server.ip_address = ip_address
        server.ssh_user = ssh_user
        server.ssh_port = ssh_port
        
        # Update authentication based on method
        if auth_method == 'key':
            if ssh_key:  # Only update if provided (otherwise keep existing)
                server.ssh_key = ssh_key
            server.ssh_password = None
        else:
            if ssh_password:  # Only update if provided
                server.ssh_password = ssh_password
            server.ssh_key = None
        
        db.session.commit()
        
        # Check connectivity if requested
        if verify_connection:
            if ServerManager.check_connectivity(server):
                flash(f'Server {name} updated successfully and connectivity verified', 'success')
            else:
                flash(f'Server {name} updated but connectivity check failed', 'warning')
        else:
            flash(f'Server {name} updated successfully', 'success')
        
        return redirect(url_for('servers.index'))
    
    # Get server logs for display
    logs = ServerLog.query.filter_by(server_id=server_id).order_by(ServerLog.created_at.desc()).limit(20).all()
    
    return render_template('servers/edit.html', server=server, logs=logs)

@bp.route('/<int:server_id>/delete', methods=['POST'])
@login_required
def delete(server_id):
    """Handle server deletion."""
    server = Server.query.get_or_404(server_id)
    
    # Check if server has associated domain groups
    if server.domain_groups:
        flash(f'Cannot delete server {server.name} because it has associated domain groups. Remove these associations first.', 'danger')
        return redirect(url_for('servers.index'))
    
    # Delete server logs
    ServerLog.query.filter_by(server_id=server_id).delete()
    
    # Delete server
    db.session.delete(server)
    db.session.commit()
    
    flash(f'Server {server.name} deleted successfully', 'success')
    return redirect(url_for('servers.index'))

@bp.route('/<int:server_id>/check', methods=['GET'])
@login_required
def check_connectivity(server_id):
    """Check server connectivity."""
    server = Server.query.get_or_404(server_id)
    
    if ServerManager.check_connectivity(server):
        flash(f'Connectivity check successful for server {server.name}', 'success')
    else:
        flash(f'Connectivity check failed for server {server.name}', 'danger')
    
    return redirect(url_for('servers.index'))

@bp.route('/groups/create', methods=['POST'])
@login_required
def create_group():
    """Create a new server group."""
    name = request.form.get('name')
    description = request.form.get('description', '')
    
    if not name:
        flash('Group name is required', 'danger')
        return redirect(url_for('servers.index'))
    
    # Check if group already exists
    existing_group = ServerGroup.query.filter_by(name=name).first()
    if existing_group:
        flash(f'Group with name "{name}" already exists', 'danger')
        return redirect(url_for('servers.index'))
    
    group = ServerGroup(name=name, description=description)
    db.session.add(group)
    
    # Add selected servers to the group if any
    server_ids = request.form.getlist('servers')
    if server_ids:
        servers = Server.query.filter(Server.id.in_(server_ids)).all()
        for server in servers:
            group.servers.append(server)
    
    db.session.commit()
    flash(f'Server group "{name}" created successfully', 'success')
    return redirect(url_for('servers.index'))

@bp.route('/groups/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    """Edit a server group."""
    group = ServerGroup.query.get_or_404(group_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if not name:
            flash('Group name is required', 'danger')
            return redirect(url_for('servers.edit_group', group_id=group_id))
        
        # Check if name is changed and new name already exists
        if name != group.name:
            existing_group = ServerGroup.query.filter_by(name=name).first()
            if existing_group:
                flash(f'Group with name "{name}" already exists', 'danger')
                return redirect(url_for('servers.edit_group', group_id=group_id))
        
        group.name = name
        group.description = description
        
        # Update servers in the group
        server_ids = request.form.getlist('servers')
        
        # Remove all servers from the group
        group.servers = []
        
        # Add selected servers
        if server_ids:
            servers = Server.query.filter(Server.id.in_(server_ids)).all()
            for server in servers:
                group.servers.append(server)
        
        db.session.commit()
        flash(f'Server group "{name}" updated successfully', 'success')
        return redirect(url_for('servers.index'))
    
    # Get all servers for selection
    servers = Server.query.all()
    return render_template('servers/edit_group.html', group=group, servers=servers)

@bp.route('/groups/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    """Delete a server group."""
    group = ServerGroup.query.get_or_404(group_id)
    name = group.name
    
    # Remove group (the many-to-many relationship will be automatically handled)
    db.session.delete(group)
    db.session.commit()
    
    flash(f'Server group "{name}" deleted successfully', 'success')
    return redirect(url_for('servers.index'))

@bp.route('/<int:server_id>/groups', methods=['GET', 'POST'])
@login_required
def manage_server_groups(server_id):
    """Manage groups for a specific server."""
    server = Server.query.get_or_404(server_id)
    
    if request.method == 'POST':
        # Get selected groups from form
        group_ids = request.form.getlist('groups')
        
        # Clear current groups
        server.groups = []
        
        # Add selected groups
        if group_ids:
            groups = ServerGroup.query.filter(ServerGroup.id.in_(group_ids)).all()
            server.groups = groups
        
        db.session.commit()
        flash(f'Groups for server "{server.name}" updated successfully', 'success')
        return redirect(url_for('servers.index'))
    
    # Get all available groups
    groups = ServerGroup.query.all()
    return render_template('servers/manage_groups.html', server=server, groups=groups)
