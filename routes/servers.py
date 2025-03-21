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
            status='pending'
        )
        
        # Устанавливаем пароль если используется аутентификация по паролю
        if auth_method == 'password' and ssh_password:
            server.set_ssh_password(ssh_password)
            
            # Временно храним пароль в памяти для проверки соединения
            if verify_connection:
                server._temp_password = ssh_password
        
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
        
        # Получаем данные биллинга
        comment = request.form.get('comment')
        billing_provider = request.form.get('billing_provider')
        billing_login = request.form.get('billing_login')
        billing_password = request.form.get('billing_password')
        payment_date_str = request.form.get('payment_date')
        
        # Преобразуем строку даты в объект Date
        from datetime import datetime
        payment_date = None
        if payment_date_str:
            try:
                payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты оплаты. Используйте формат ГГГГ-ММ-ДД', 'danger')
                return render_template('servers/edit.html', server=server, logs=[])
        
        # Update server information
        server.name = name
        server.ip_address = ip_address
        server.ssh_user = ssh_user
        server.ssh_port = ssh_port
        
        # Обновляем данные биллинга
        server.comment = comment
        server.billing_provider = billing_provider
        server.billing_login = billing_login
        if billing_password:
            server.set_billing_password(billing_password)
        
        # Обновляем дату оплаты и сбрасываем флаг отправки напоминания при изменении даты
        if payment_date and (not server.payment_date or server.payment_date != payment_date):
            server.payment_date = payment_date
            server.payment_reminder_sent = False
        
        # Update authentication based on method
        if auth_method == 'key':
            if ssh_key:  # Only update if provided (otherwise keep existing)
                server.ssh_key = ssh_key
            server.ssh_password_hash = None
        else:
            if ssh_password:  # Only update if provided
                server.set_ssh_password(ssh_password)
                # Временно храним пароль в памяти для проверки соединения
                if verify_connection:
                    server._temp_password = ssh_password
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

@bp.route('/<int:server_id>/check', methods=['GET', 'POST'])
@login_required
def check_connectivity(server_id):
    """Check server connectivity."""
    server = Server.query.get_or_404(server_id)
    
    # Для серверов с шифрованным паролем используем его для проверки
    if server.ssh_encrypted_password:
        try:
            # Если пароль уже зашифрован, используем его
            if ServerManager.check_connectivity(server):
                flash(f'Подключение к серверу {server.name} успешно проверено', 'success')
            else:
                flash(f'Ошибка подключения к серверу {server.name}', 'danger')
            return redirect(url_for('servers.index'))
        except Exception as e:
            flash(f'Ошибка проверки подключения: {str(e)}', 'danger')
            return redirect(url_for('servers.index'))
    
    # Для серверов с аутентификацией по паролю без зашифрованного пароля
    if not server.ssh_key and not server.ssh_encrypted_password and request.method == 'GET':
        # Отображаем форму ввода пароля
        servers = Server.query.all()
        password_servers = [s for s in servers if not s.ssh_key and not s.ssh_encrypted_password]
        key_servers = [s for s in servers if s.ssh_key]
        encrypted_servers = [s for s in servers if s.ssh_encrypted_password]
        
        return render_template('servers/check_password.html', 
                               server=server, 
                               servers=servers,
                               password_servers=password_servers,
                               key_servers=key_servers,
                               encrypted_servers=encrypted_servers)
    
    # Если используется аутентификация по паролю, получаем его из формы
    if not server.ssh_key and not server.ssh_encrypted_password and request.method == 'POST':
        password = request.form.get('ssh_password')
        if not password:
            flash('Пароль SSH необходим для проверки подключения', 'warning')
            return redirect(url_for('servers.check_connectivity', server_id=server_id))
        
        # Временно храним пароль только в оперативной памяти
        server._temp_password = password
    
    try:
        if ServerManager.check_connectivity(server):
            flash(f'Подключение к серверу {server.name} успешно проверено', 'success')
        else:
            flash(f'Ошибка подключения к серверу {server.name}', 'danger')
    except Exception as e:
        flash(f'Ошибка проверки подключения: {str(e)}', 'danger')
    
    # Очищаем временный пароль
    if hasattr(server, '_temp_password'):
        delattr(server, '_temp_password')
    
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
    
    
@bp.route('/check_passwords')
@login_required
def check_passwords():
    """Проверка шифрования паролей серверов"""
    servers = Server.query.order_by(Server.name).all()
    
    # Фильтруем серверы по типу аутентификации
    servers_with_passwords = [s for s in servers if s.ssh_password_hash and not s.ssh_key]
    servers_with_keys = [s for s in servers if s.ssh_key]
    servers_with_encrypted = [s for s in servers if s.ssh_encrypted_password]
    
    errors = []
    if servers_with_passwords and not servers_with_encrypted:
        errors.append("Обнаружены серверы с паролями, но без зашифрованных версий для автоматической проверки")
    
    return render_template('servers/check_password.html',
                           servers=servers,
                           servers_with_passwords=servers_with_passwords,
                           servers_with_keys=servers_with_keys,
                           servers_with_encrypted=servers_with_encrypted,
                           errors=errors)


@bp.route('/migrate_passwords')
@login_required
def migrate_passwords():
    """Запускает миграцию паролей в зашифрованный формат"""
    from add_encrypted_password import encrypt_existing_passwords
    
    # Запускаем миграцию с тестовым паролем (в продакшн-версии нужно запрашивать настоящие пароли)
    encrypt_existing_passwords()
    
    flash('Миграция паролей выполнена успешно. В тестовой версии для всех серверов установлен пароль "test123"', 'success')
    return redirect(url_for('servers.check_passwords'))
