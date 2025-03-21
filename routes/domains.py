import logging
import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required
from models import Domain, DomainGroup, db
from modules.domain_manager import DomainManager

bp = Blueprint('domains', __name__, url_prefix='/domains')
logger = logging.getLogger(__name__)

@bp.route('/')
@login_required
def index():
    """Show list of domains."""
    # Получаем параметр группы из запроса
    group_id = request.args.get('group_id', type=int)
    
    # Получаем все группы доменов для фильтра
    domain_groups = DomainGroup.query.all()
    
    if group_id:
        # Если указана группа, фильтруем домены по этой группе
        group = DomainGroup.query.get_or_404(group_id)
        domains = group.domains.all()
    else:
        # Иначе показываем все домены
        domains = Domain.query.all()
    
    return render_template('domains/index.html', 
                          domains=domains, 
                          domain_groups=domain_groups,
                          selected_group_id=group_id)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Handle domain creation."""
    if request.method == 'POST':
        name = request.form.get('name')
        target_ip = request.form.get('target_ip')
        server_id = request.form.get('server_id')
        target_port = request.form.get('target_port', 80, type=int)
        ssl_enabled = 'ssl_enabled' in request.form
        
        # Если выбран сервер, используем его IP-адрес
        if server_id and not target_ip:
            from models import Server
            server = Server.query.get(server_id)
            if server:
                target_ip = server.ip_address
        
        # Validate required fields
        if not name or not target_ip:
            flash('Domain name and target IP are required', 'danger')
            return redirect(url_for('domains.create'))
        
        # Check if domain already exists
        existing_domain = Domain.query.filter_by(name=name).first()
        if existing_domain:
            flash(f'Domain {name} already exists', 'danger')
            return redirect(url_for('domains.create'))
        
        # Получаем ожидаемые NS-записи
        expected_nameservers = request.form.get('expected_nameservers', '')
        
        # Create domain
        domain = Domain(
            name=name,
            target_ip=target_ip,
            target_port=target_port,
            ssl_enabled=ssl_enabled,
            expected_nameservers=expected_nameservers
        )
        
        db.session.add(domain)
        db.session.commit()
        
        # Add to domain groups if specified
        group_ids = request.form.getlist('groups[]')
        if group_ids:
            for group_id in group_ids:
                group = DomainGroup.query.get(group_id)
                if group:
                    group.domains.append(domain)
            
            db.session.commit()
            flash(f'Domain {name} created and added to {len(group_ids)} group(s)', 'success')
        else:
            flash(f'Domain {name} created successfully', 'success')
        
        return redirect(url_for('domains.index'))
    
    # Get all domain groups for dropdown
    domain_groups = DomainGroup.query.all()
    
    # Get all servers for dropdown
    from models import Server
    servers = Server.query.all()
    
    return render_template('domains/create.html', 
                          domain_groups=domain_groups, 
                          servers=servers)

@bp.route('/<int:domain_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(domain_id):
    """Handle domain editing."""
    domain = Domain.query.get_or_404(domain_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        target_ip = request.form.get('target_ip')
        server_id = request.form.get('server_id')
        target_port = request.form.get('target_port', 80, type=int)
        ssl_enabled = 'ssl_enabled' in request.form
        
        # Если выбран сервер, используем его IP-адрес
        if server_id and not target_ip:
            from models import Server
            server = Server.query.get(server_id)
            if server:
                target_ip = server.ip_address
        
        # Validate required fields
        if not name or not target_ip:
            flash('Domain name and target IP are required', 'danger')
            return redirect(url_for('domains.edit', domain_id=domain_id))
        
        # Check if domain name changed and if new name already exists
        if name != domain.name:
            existing_domain = Domain.query.filter_by(name=name).first()
            if existing_domain:
                flash(f'Domain {name} already exists', 'danger')
                return redirect(url_for('domains.edit', domain_id=domain_id))
        
        # Получаем ожидаемые NS-записи
        expected_nameservers = request.form.get('expected_nameservers', '')
        
        # Update domain
        domain.name = name
        domain.target_ip = target_ip
        domain.target_port = target_port
        domain.ssl_enabled = ssl_enabled
        domain.expected_nameservers = expected_nameservers
        
        # Update domain groups
        domain.groups = []
        group_ids = request.form.getlist('groups[]')
        if group_ids:
            for group_id in group_ids:
                group = DomainGroup.query.get(group_id)
                if group:
                    domain.groups.append(group)
        
        db.session.commit()
        flash(f'Domain {name} updated successfully', 'success')
        
        return redirect(url_for('domains.index'))
    
    # Get all domain groups for dropdown
    domain_groups = DomainGroup.query.all()
    
    # Get all servers for dropdown
    from models import Server
    servers = Server.query.all()
    
    return render_template('domains/edit.html', 
                          domain=domain, 
                          domain_groups=domain_groups, 
                          servers=servers)

@bp.route('/<int:domain_id>/delete', methods=['POST'])
@login_required
def delete(domain_id):
    """Handle domain deletion."""
    domain = Domain.query.get_or_404(domain_id)
    name = domain.name
    
    # Remove domain from all groups
    domain.groups = []
    
    # Delete domain
    db.session.delete(domain)
    db.session.commit()
    
    flash(f'Domain {name} deleted successfully', 'success')
    return redirect(url_for('domains.index'))

@bp.route('/<int:domain_id>/nameservers', methods=['GET', 'POST'])
@login_required
def nameservers(domain_id):
    """Управление NS-записями домена."""
    domain = Domain.query.get_or_404(domain_id)
    
    if request.method == 'POST':
        expected_nameservers = request.form.get('expected_nameservers', '')
        if DomainManager.update_expected_nameservers(domain_id, expected_nameservers):
            flash(f'Ожидаемые NS-записи для домена {domain.name} обновлены', 'success')
        else:
            flash('Произошла ошибка при обновлении NS-записей', 'danger')
        
        return redirect(url_for('domains.nameservers', domain_id=domain_id))
    
    # Получаем текущие NS-записи для отображения
    actual_ns = []
    if domain.actual_nameservers:
        actual_ns = domain.actual_nameservers.split(',')
    
    return render_template('domains/nameservers.html', domain=domain, actual_ns=actual_ns)

@bp.route('/<int:domain_id>/check-ns', methods=['POST'])
@login_required
def check_ns(domain_id):
    """Проверка NS-записей домена."""
    domain = Domain.query.get_or_404(domain_id)
    
    if DomainManager.check_domain_ns_status(domain_id):
        flash('Проверка NS-записей завершена успешно', 'success')
    else:
        if domain.ns_status == 'mismatch':
            flash('Ожидаемые NS-записи не все обнаружены в фактическом списке NS. Убедитесь, что все NS-серверы настроены правильно.', 'warning')
        else:
            flash('Произошла ошибка при проверке NS-записей', 'danger')
    
    return redirect(url_for('domains.nameservers', domain_id=domain_id))

@bp.route('/check-all-ns', methods=['POST'])
@login_required
def check_all_ns():
    """Проверка NS-записей всех доменов."""
    results = DomainManager.check_all_domains_ns_status()
    
    if results['ok'] > 0:
        message_success = f"{results['ok']} доменов с корректными NS-записями"
        flash(message_success, 'success')
        
    if results['mismatch'] > 0:
        message_warning = f"{results['mismatch']} доменов имеют несоответствие NS-записей. Проверьте настройки NS-серверов."
        flash(message_warning, 'warning')
        
    if results['error'] > 0:
        message_error = f"{results['error']} доменов имеют ошибки при проверке NS-записей"
        flash(message_error, 'danger')
    
    if results['ok'] + results['mismatch'] + results['error'] == 0:
        flash("Нет доменов с указанными ожидаемыми NS-записями для проверки", 'info')
    
    return redirect(url_for('domains.index'))

@bp.route('/api/check-nameservers/<domain_name>', methods=['GET'])
@login_required
def api_check_nameservers(domain_name):
    """API для проверки NS-записей по имени домена."""
    try:
        nameservers = DomainManager.check_nameservers(domain_name)
        return jsonify({
            'success': True,
            'nameservers': nameservers
        })
    except Exception as e:
        logger.error(f"API error checking nameservers for {domain_name}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@bp.route('/<int:domain_id>/ffpanel', methods=['GET', 'POST'])
@login_required
def ffpanel(domain_id):
    """Управление интеграцией домена с FFPanel."""
    domain = Domain.query.get_or_404(domain_id)
    
    # Проверяем, установлен ли токен FFPanel
    ffpanel_token = os.environ.get('FFPANEL_TOKEN')
    if not ffpanel_token:
        flash('Не настроен токен FFPanel API. Пожалуйста, добавьте FFPANEL_TOKEN в переменные окружения.', 'danger')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Синхронизация домена с FFPanel
        if action == 'sync':
            # Обновляем параметры домена для FFPanel
            domain.ffpanel_port = request.form.get('ffpanel_port', '80')
            domain.ffpanel_port_out = request.form.get('ffpanel_port_out', '80')
            domain.ffpanel_port_ssl = request.form.get('ffpanel_port_ssl', '443')
            domain.ffpanel_port_out_ssl = request.form.get('ffpanel_port_out_ssl', '443')
            domain.ffpanel_dns = request.form.get('ffpanel_dns', '')
            db.session.commit()
            
            # Запускаем синхронизацию
            result = DomainManager.sync_domain_with_ffpanel(domain_id)
            
            if result['success']:
                flash(result['message'], 'success')
            else:
                flash(result['message'], 'danger')
                
        # Удаление домена из FFPanel
        elif action == 'delete':
            result = DomainManager.delete_domain_from_ffpanel(domain_id)
            
            if result['success']:
                flash(result['message'], 'success')
            else:
                flash(result['message'], 'danger')
        
        return redirect(url_for('domains.ffpanel', domain_id=domain_id))
    
    return render_template('domains/ffpanel.html', domain=domain)

@bp.route('/ffpanel/import', methods=['GET', 'POST'])
@login_required
def ffpanel_import():
    """Импорт доменов из FFPanel."""
    
    # Проверяем, установлен ли токен FFPanel
    ffpanel_token = os.environ.get('FFPANEL_TOKEN')
    if not ffpanel_token:
        flash('Не настроен токен FFPanel API. Пожалуйста, добавьте FFPANEL_TOKEN в переменные окружения.', 'danger')
        return redirect(url_for('domains.index'))
    
    if request.method == 'POST':
        # Запускаем импорт доменов
        stats = DomainManager.import_domains_from_ffpanel()
        
        flash(stats['message'], 'info')
        
        if stats['imported'] > 0 or stats['updated'] > 0:
            flash(f"Импортировано новых доменов: {stats['imported']}, обновлено существующих: {stats['updated']}", 'success')
        
        if stats['failed'] > 0:
            flash(f"Ошибок при импорте: {stats['failed']}", 'warning')
            
            # Отображаем детали ошибок
            if 'errors' in stats and stats['errors']:
                for error in stats['errors']:
                    flash(f"Детали ошибки: {error}", 'danger')
            
        return redirect(url_for('domains.index'))
    
    return render_template('domains/ffpanel_import.html')
