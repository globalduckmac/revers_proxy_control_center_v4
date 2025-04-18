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
    show_ungrouped = request.args.get('show_ungrouped') == '1'
    
    # Получаем все группы доменов для фильтра
    domain_groups = DomainGroup.query.all()
    
    if group_id:
        # Если указана группа, фильтруем домены по этой группе
        group = DomainGroup.query.get_or_404(group_id)
        domains = group.domains.all()
    elif show_ungrouped:
        # Показываем только домены без групп
        from sqlalchemy import select, not_, exists

        # Находим домены, которые не имеют связей в таблице domain_group_association
        ungrouped_domains = []
        
        # Получаем все домены
        all_domains = Domain.query.all()
        
        # Фильтруем только те, у которых нет групп
        for domain in all_domains:
            if not domain.groups:
                ungrouped_domains.append(domain)
                
        domains = ungrouped_domains
    else:
        # Иначе показываем все домены
        domains = Domain.query.all()
    
    return render_template('domains/index.html', 
                          domains=domains, 
                          domain_groups=domain_groups,
                          selected_group_id=group_id,
                          show_ungrouped=show_ungrouped)

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
        
        # Получаем настройки FFPanel
        ffpanel_enabled = 'ffpanel_enabled' in request.form
        ffpanel_target_ip = None
        
        if ffpanel_enabled:
            # Проверяем, был ли выбран сервер для FFPanel
            server_id = request.form.get('server_id')
            if server_id:
                # Если выбран сервер, используем его IP-адрес для FFPanel
                from models import Server
                server = Server.query.get(server_id)
                if server:
                    ffpanel_target_ip = server.ip_address
            else:
                # Иначе используем введенный вручную IP
                ffpanel_target_ip = request.form.get('ffpanel_target_ip')
            
            # Если FFPanel включен, но не указан специальный IP, используем основной target_ip
            if not ffpanel_target_ip:
                ffpanel_target_ip = target_ip
            
        # Create domain
        domain = Domain(
            name=name,
            target_ip=target_ip,
            target_port=target_port,
            ssl_enabled=ssl_enabled,
            expected_nameservers=expected_nameservers,
            ffpanel_enabled=ffpanel_enabled,
            ffpanel_target_ip=ffpanel_target_ip
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

@bp.route('/<int:domain_id>', methods=['GET'])
@login_required
def view(domain_id):
    """Просмотр информации о домене."""
    domain = Domain.query.get_or_404(domain_id)
    
    # Получаем информацию о сервере домена
    server = None
    if domain.server_id:
        from models import Server
        server = Server.query.get(domain.server_id)
    
    # Получаем группы доменов для отображения
    domain_groups = DomainGroup.query.all()
    
    # Получаем задачи для домена (если есть)
    domain_tasks = []  # Здесь можно добавить загрузку задач, связанных с доменом
    
    return render_template(
        'domains/view.html',
        domain=domain,
        server=server,
        domain_groups=domain_groups,
        domain_tasks=domain_tasks
    )

@bp.route('/<int:domain_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(domain_id):
    """Handle domain editing."""
    domain = Domain.query.get_or_404(domain_id)
    
    # Получаем список серверов и внешних серверов для выбора FFPanel Target IP
    from models import Server, ExternalServer
    servers = Server.query.all()
    external_servers = ExternalServer.query.all()
    
    if request.method == 'POST':
        # Отладка: выводим все данные формы
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"FORM DATA for domain_id {domain_id}: {request.form}")
        
        name = request.form.get('name')
        target_ip = request.form.get('target_ip')
        target_port = request.form.get('target_port', 80, type=int)
        ssl_enabled = 'ssl_enabled' in request.form
        
        # Обработка FFPanel Target IP в зависимости от выбранного источника
        ffpanel_ip_source = request.form.get('ffpanel_ip_source', 'same')
        
        if ffpanel_ip_source == 'same':
            # Используем тот же IP, что и у домена
            ffpanel_target_ip = target_ip
        elif ffpanel_ip_source == 'server':
            # Получаем IP из выбранного сервера
            server_id = request.form.get('ffpanel_server_id')
            if server_id:
                from models import Server
                server = Server.query.get(server_id)
                if server:
                    ffpanel_target_ip = server.ip_address
                else:
                    ffpanel_target_ip = domain.ffpanel_target_ip
            else:
                ffpanel_target_ip = domain.ffpanel_target_ip
        elif ffpanel_ip_source == 'external_server':
            # Получаем IP из выбранного внешнего сервера
            external_server_id = request.form.get('ffpanel_external_server_id')
            if external_server_id:
                from models import ExternalServer
                external_server = ExternalServer.query.get(external_server_id)
                if external_server:
                    ffpanel_target_ip = external_server.ip_address
                else:
                    ffpanel_target_ip = domain.ffpanel_target_ip
            else:
                ffpanel_target_ip = domain.ffpanel_target_ip
        elif ffpanel_ip_source == 'manual':
            # Используем вручную введенный IP
            ffpanel_target_ip = request.form.get('ffpanel_target_ip_manual')
        else:
            # Значение по умолчанию
            ffpanel_target_ip = domain.ffpanel_target_ip
        
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
        
        # Получаем настройки FFPanel
        ffpanel_enabled = 'ffpanel_enabled' in request.form
        ffpanel_target_ip = None
        
        if ffpanel_enabled:
            # Получаем источник IP для FFPanel
            ffpanel_ip_source = request.form.get('ffpanel_ip_source', 'manual')
            logger.info(f"FFPanel IP Source: {ffpanel_ip_source}")
            
            if ffpanel_ip_source == 'server':
                # Если выбран стандартный сервер
                server_id = request.form.get('ffpanel_server_id')
                if server_id:
                    server = Server.query.get(server_id)
                    if server:
                        ffpanel_target_ip = server.ip_address
                        logger.info(f"Using server IP for FFPanel: {ffpanel_target_ip} (server_id: {server_id})")
            elif ffpanel_ip_source == 'external_server':
                # Если выбран внешний сервер
                ext_server_id = request.form.get('ffpanel_external_server_id')
                if ext_server_id:
                    ext_server = ExternalServer.query.get(ext_server_id)
                    if ext_server:
                        ffpanel_target_ip = ext_server.ip_address
                        logger.info(f"Using external server IP for FFPanel: {ffpanel_target_ip} (ext_server_id: {ext_server_id})")
            elif ffpanel_ip_source == 'same':
                # Если используется тот же IP что и у домена
                ffpanel_target_ip = target_ip
                logger.info(f"Using same IP for FFPanel as domain: {ffpanel_target_ip}")
            else:
                # Иначе используем введенный вручную IP
                ffpanel_target_ip = request.form.get('ffpanel_target_ip')
                logger.info(f"Using manually entered IP for FFPanel: {ffpanel_target_ip}")
            
            # Если FFPanel включен, но не указан специальный IP, используем основной target_ip
            if not ffpanel_target_ip:
                ffpanel_target_ip = target_ip
                logger.info(f"Falling back to domain IP for FFPanel: {ffpanel_target_ip}")
        
        # Update domain
        domain.name = name
        domain.target_ip = target_ip
        domain.target_port = target_port
        domain.ssl_enabled = ssl_enabled
        domain.expected_nameservers = expected_nameservers
        domain.ffpanel_enabled = ffpanel_enabled
        domain.ffpanel_target_ip = ffpanel_target_ip
        
        # Update domain groups
        # Очищаем существующие группы перед обновлением
        from sqlalchemy.orm import joinedload
        
        # Получаем текущие группы для домена (для дебага)
        current_domain = Domain.query.options(joinedload(Domain.groups)).get(domain_id)
        logger.info(f"Current domain groups before update: {[g.name for g in current_domain.groups]}")
        
        # Очищаем группы
        domain.groups = []
        
        # Получаем группы из формы
        logger.info(f"Form keys: {list(request.form.keys())}")
        group_ids = request.form.getlist('groups[]')
        
        # Если нет групп в groups[], попробуем domain_groups[] для совместимости со старыми формами
        if not group_ids:
            group_ids = request.form.getlist('domain_groups[]')
            
        logger.info(f"Group IDs from form: {group_ids}")
        
        # Применяем группы к домену
        if group_ids:
            for group_id in group_ids:
                try:
                    group = DomainGroup.query.get(group_id)
                    if group:
                        logger.info(f"Adding domain {domain_id} to group {group.id} ({group.name})")
                        domain.groups.append(group)
                    else:
                        logger.warning(f"Group with ID {group_id} not found!")
                except Exception as e:
                    logger.error(f"Error adding group {group_id} to domain: {str(e)}")
        else:
            logger.warning(f"No groups selected for domain {domain_id}")
        
        # Сохраняем изменения немедленно
        try:
            db.session.commit()
            # Получаем актуальные группы домена после сохранения
            domain_after_update = Domain.query.options(joinedload(Domain.groups)).get(domain_id)
            logger.info(f"Domain groups updated. New groups: {[g.name for g in domain_after_update.groups]}")
        except Exception as e:
            logger.error(f"Error saving domain groups: {str(e)}")
            db.session.rollback()
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
                          servers=servers,
                          external_servers=external_servers)

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
    import logging
    import traceback
    
    logger = logging.getLogger(__name__)
    
    try:
        # Оборачиваем весь блок получения домена в отдельную сессию
        with db.session.begin_nested():
            domain = Domain.query.get(domain_id)
            if not domain:
                flash(f'Домен с ID {domain_id} не найден', 'danger')
                return redirect(url_for('domains.index'))
            
            # Для логирования используем маскированное имя
            from modules.telegram_notifier import mask_domain_name
            masked_domain = mask_domain_name(domain.name)
            logger.info(f"Начинаем проверку NS для домена {masked_domain} (ID: {domain_id})")
    except Exception as e:
        logger.error(f"Ошибка при получении домена {domain_id}: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        flash(f'Не удалось получить информацию о домене: {str(e)}', 'danger')
        return redirect(url_for('domains.index'))
    
    try:
        # Выполняем проверку в отдельном блоке
        result = DomainManager.check_domain_ns_status(domain_id)
        
        # После проверки получаем обновленный статус
        try:
            updated_domain = Domain.query.get(domain_id)
            if result:
                flash('Проверка NS-записей завершена успешно', 'success')
            elif updated_domain and updated_domain.ns_status == 'mismatch':
                flash('Ожидаемые NS-записи не все обнаружены в фактическом списке NS. Убедитесь, что все NS-серверы настроены правильно.', 'warning')
            else:
                flash('Произошла ошибка при проверке NS-записей или статус не определен', 'danger')
                
        except Exception as db_error:
            logger.error(f"Ошибка при получении обновленного статуса домена {domain_id}: {str(db_error)}")
            logger.error(traceback.format_exc())
            db.session.rollback()
            flash('Ошибка при получении обновленного статуса домена', 'danger')
    except Exception as e:
        logger.error(f"Ошибка при проверке NS для домена {domain_id}: {str(e)}")
        logger.error(traceback.format_exc())
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(f"Ошибка при откате транзакции: {str(rollback_error)}")
        flash(f'Ошибка при проверке NS-записей: {str(e)}', 'danger')
    
    return redirect(url_for('domains.nameservers', domain_id=domain_id))

@bp.route('/<int:domain_id>/setup-ssl', methods=['GET', 'POST'])
@login_required
def setup_ssl_for_domain(domain_id):
    """Настраивает SSL-сертификат для отдельного домена."""
    from models import Domain, Server, ServerLog, ProxyConfig, db
    from modules.deployment import DeploymentManager
    from flask import current_app
    import logging
    
    logger = logging.getLogger(__name__)
    
    domain = Domain.query.get_or_404(domain_id)
    
    # Проверяем, что SSL включен для домена
    if not domain.ssl_enabled:
        flash(f'SSL не включен для домена {domain.name}. Включите SSL в настройках домена.', 'warning')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Проверяем, что домен привязан к группе и серверу
    if not domain.groups:
        flash(f'Домен {domain.name} не привязан ни к одной группе. Привяжите домен к группе сервера.', 'warning')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Находим сервер для домена (берем первую группу с сервером)
    server = None
    for group in domain.groups:
        if group.server:
            server = group.server
            break
    
    if not server:
        flash(f'Домен {domain.name} не привязан к серверу. Привяжите домен к группе с сервером.', 'warning')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Для GET запроса просто показываем страницу подтверждения
    if request.method == 'GET':
        # Логи установки SSL для домена
        logs = ServerLog.query.filter_by(
            server_id=server.id,
            action='ssl_setup'
        ).order_by(ServerLog.created_at.desc()).limit(5).all()
        
        # Email администратора из конфигурации
        admin_email = current_app.config.get('ADMIN_EMAIL', 'admin@example.com')
        
        return render_template(
            'domains/setup_ssl.html',
            domain=domain,
            server=server,
            logs=logs,
            admin_email=admin_email
        )
    
    # Для POST запроса выполняем установку SSL
    # Получаем email из формы
    admin_email = request.form.get('admin_email', current_app.config.get('ADMIN_EMAIL', 'admin@example.com'))
    
    # Временно обновляем конфигурацию с указанным email
    current_app.config['ADMIN_EMAIL'] = admin_email
    
    # Устанавливаем SSL через Certbot
    try:
        # Используем модифицированную функцию, которая теперь поддерживает один домен
        success = DeploymentManager.setup_ssl_certbot(server, domain)
        
        if success:
            # После успешной установки SSL сертификата перегенерируем и обновляем конфигурацию Nginx
            from modules.proxy_manager import ProxyManager
            
            logger.info(f"SSL установлен успешно, перегенерируем конфигурацию Nginx для сервера {server.name}")
            
            # Получаем последнюю конфигурацию прокси для сервера
            proxy_config = ProxyConfig.query.filter_by(server_id=server.id).order_by(ProxyConfig.id.desc()).first()
            
            if proxy_config:
                # Запускаем деплой конфигурации только для этого домена
                proxy_manager = ProxyManager(current_app.config.get('NGINX_TEMPLATES_PATH', 'templates/nginx'))
                proxy_manager.deploy_proxy_config(server.id, domain.id)
                
                flash(f'SSL сертификат успешно установлен для домена {domain.name} и конфигурация Nginx обновлена', 'success')
            else:
                # Если конфигурации нет, создаем новую
                proxy_config = ProxyConfig(server_id=server.id, status='pending')
                db.session.add(proxy_config)
                db.session.commit()
                
                proxy_manager = ProxyManager(current_app.config.get('NGINX_TEMPLATES_PATH', 'templates/nginx'))
                proxy_manager.deploy_proxy_config(server.id, domain.id)
                
                flash(f'SSL сертификат успешно установлен для домена {domain.name} и создана новая конфигурация Nginx', 'success')
        else:
            flash(f'Не удалось установить SSL сертификат для домена {domain.name}', 'danger')
    except Exception as e:
        logger.exception(f"Ошибка при установке SSL сертификата для домена {domain.name}")
        flash(f'Ошибка при установке SSL сертификата: {str(e)}', 'danger')
    
    return redirect(url_for('domains.edit', domain_id=domain_id))

@bp.route('/check-all-ns', methods=['POST'])
@login_required
def check_all_ns():
    """Проверка NS-записей всех доменов."""
    import logging
    import traceback
    import html
    
    logger = logging.getLogger(__name__)
    
    logger.info("Начинаем проверку NS-записей всех доменов")
    
    try:
        # Выполняем проверку с отельной обработкой отката транзакций
        try:
            results = DomainManager.check_all_domains_ns_status()
            logger.info(f"Результаты проверки всех NS-записей: {results}")
            
            # Дополнительная проверка на валидность результатов
            if not isinstance(results, dict):
                logger.error(f"Неверный формат результатов: {type(results)}")
                raise ValueError("Результаты проверки имеют неверный формат")
                
            # Безопасно получаем количество проверенных доменов 
            ok_count = results.get('ok', 0)
            mismatch_count = results.get('mismatch', 0)
            error_count = results.get('error', 0)
            
            # Формируем сообщения для пользователя
            if ok_count > 0:
                message_success = f"{ok_count} доменов с корректными NS-записями"
                flash(message_success, 'success')
                
            if mismatch_count > 0:
                message_warning = f"{mismatch_count} доменов имеют несоответствие NS-записей. Проверьте настройки NS-серверов."
                flash(message_warning, 'warning')
                
            if error_count > 0:
                message_error = f"{error_count} доменов имеют ошибки при проверке NS-записей"
                flash(message_error, 'danger')
            
            total_count = ok_count + mismatch_count + error_count
            if total_count == 0:
                flash("Нет доменов с указанными ожидаемыми NS-записями для проверки", 'info')
                
        except Exception as inner_error:
            error_str = html.escape(str(inner_error))
            logger.error(f"Ошибка при выполнении проверки всех NS-записей: {error_str}")
            logger.error(traceback.format_exc())
            
            try:
                db.session.rollback()
            except Exception as rollback_error:
                logger.error(f"Ошибка при откате транзакции: {html.escape(str(rollback_error))}")
                
            # Создаем безопасное сообщение об ошибке для пользователя
            flash('Произошла ошибка при проверке NS-записей доменов. Пожалуйста, попробуйте позже.', 'danger')
            return redirect(url_for('domains.index'))
            
    except Exception as e:
        # Обработка и экранирование возможных ошибок
        error_message = html.escape(str(e))
        logger.error(f"Критическая ошибка при проверке всех NS-записей: {error_message}")
        logger.error(traceback.format_exc())
        
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(f"Критическая ошибка при откате транзакции: {html.escape(str(rollback_error))}")
            
        # Отображаем более информативное сообщение
        if 'database' in error_message.lower() or 'db' in error_message.lower() or 'sql' in error_message.lower():
            flash('Ошибка соединения с базой данных при проверке NS-записей. Пожалуйста, попробуйте позже.', 'danger')
        elif 'unicode' in error_message.lower() or 'encode' in error_message.lower() or 'decode' in error_message.lower():
            flash('Ошибка кодировки при проверке NS-записей. Возможно, в именах доменов используются специальные символы.', 'danger')
        else:
            # Безопасно отображаем только общее сообщение без технических деталей
            flash('Произошла ошибка при проверке NS-записей. Пожалуйста, попробуйте позже.', 'danger')
    
    return redirect(url_for('domains.index'))

@bp.route('/api/check-nameservers/<domain_name>', methods=['GET'])
@login_required
def api_check_nameservers(domain_name):
    """API для проверки NS-записей по имени домена."""
    import traceback
    import html
    
    # Создаем безопасную строку имени домена для логирования
    from modules.telegram_notifier import mask_domain_name
    
    try:
        # Безопасно обрабатываем имя домена, экранируя возможные проблемные символы
        masked_domain_name = mask_domain_name(domain_name.strip())
        
        # Проверяем допустимость имени домена
        if not domain_name or len(domain_name.strip()) == 0:
            logger.error("API error: Empty domain name provided")
            return jsonify({
                'success': False,
                'error': 'Необходимо указать имя домена'
            }), 400
        
        # Выполняем проверку NS-записей с расширенным логированием
        try:
            logger.info(f"API checking nameservers for domain: {masked_domain_name}")
            nameservers = DomainManager.check_nameservers(domain_name)
            
            # Проверка результатов
            if not isinstance(nameservers, list):
                raise ValueError(f"Unexpected nameservers format: {type(nameservers)}")
                
            logger.info(f"API successfully checked nameservers for {masked_domain_name}: {nameservers}")
            return jsonify({
                'success': True,
                'nameservers': nameservers
            })
            
        except Exception as dns_error:
            # Детальное логирование ошибки DNS-проверки
            error_text = html.escape(str(dns_error))
            logger.error(f"DNS error checking nameservers for {masked_domain_name}: {error_text}")
            logger.error(traceback.format_exc())
            
            return jsonify({
                'success': False,
                'error': 'Ошибка при проверке NS-записей. Проверьте правильность имени домена.'
            }), 400
            
    except Exception as e:
        # Логируем общую ошибку, но не показываем технические детали пользователю
        error_text = html.escape(str(e))
        logger.error(f"API critical error checking nameservers: {error_text}")
        logger.error(traceback.format_exc())
        
        # Проверка наличия ошибки соединения с базой данных
        if 'database' in error_text.lower() or 'db' in error_text.lower() or 'sql' in error_text.lower():
            logger.error(f"Database connection error during nameserver check")
            try:
                db.session.rollback()
            except Exception as rollback_error:
                logger.error(f"Failed to rollback: {html.escape(str(rollback_error))}")
            
            return jsonify({
                'success': False,
                'error': 'Ошибка соединения с базой данных. Пожалуйста, попробуйте позже.'
            }), 500
        
        # Ошибки кодировки Unicode
        elif 'unicode' in error_text.lower() or 'encode' in error_text.lower() or 'decode' in error_text.lower():
            return jsonify({
                'success': False,
                'error': 'Ошибка кодировки при проверке домена. Проверьте, что имя домена не содержит специальных символов.'
            }), 400
            
        # Для остальных ошибок возвращаем универсальное сообщение
        return jsonify({
            'success': False,
            'error': 'Ошибка при проверке NS-записей. Пожалуйста, попробуйте позже.'
        }), 500

@bp.route('/<int:domain_id>/ffpanel_sync', methods=['POST'])
@login_required
def ffpanel_sync(domain_id):
    """Синхронизация домена с FFPanel."""
    from modules.ffpanel_api import FFPanelAPI
    import logging
    import os
    
    logger = logging.getLogger(__name__)
    logger.info(f"Начало синхронизации домена {domain_id} с FFPanel")
    
    domain = Domain.query.get_or_404(domain_id)
    
    # Проверяем, что FFPanel включен для домена
    if not domain.ffpanel_enabled:
        flash('FFPanel интеграция не включена для этого домена. Включите её в настройках.', 'warning')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Проверяем, настроен ли токен FFPanel
    ffpanel_token = os.environ.get('FFPANEL_TOKEN')
    if not ffpanel_token:
        from models import SystemSetting
        ffpanel_token = SystemSetting.get_value('ffpanel_token')
        
    if not ffpanel_token:
        flash('Не настроен токен FFPanel API. Пожалуйста, добавьте FFPANEL_TOKEN в переменные окружения или настройках системы.', 'danger')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Определяем IP-адрес и порт для FFPanel
    # Используем тот же источник IP-адреса, что и в форме редактирования домена
    if domain.ffpanel_target_ip == domain.target_ip:
        # Если IP совпадает с доменом, используем его
        target_ip = domain.target_ip
        logger.info(f"Использую тот же IP, что и у домена: {target_ip} для домена {domain.name}")
    elif domain.ffpanel_target_ip:
        # Проверяем, соответствует ли IP какому-то серверу или внешнему серверу
        from models import Server, ExternalServer
        server = Server.query.filter_by(ip_address=domain.ffpanel_target_ip).first()
        ext_server = ExternalServer.query.filter_by(ip_address=domain.ffpanel_target_ip).first()
        
        if server:
            logger.info(f"Использую IP сервера {server.name}: {domain.ffpanel_target_ip} для домена {domain.name}")
        elif ext_server:
            logger.info(f"Использую IP внешнего сервера {ext_server.name}: {domain.ffpanel_target_ip} для домена {domain.name}")
        else:
            logger.info(f"Использую указанный вручную IP: {domain.ffpanel_target_ip} для домена {domain.name}")
            
        target_ip = domain.ffpanel_target_ip
    else:
        # Если ffpanel_target_ip не указан, используем стандартный target_ip
        target_ip = domain.target_ip
        logger.info(f"Использую стандартный Target IP: {target_ip} для домена {domain.name}")
    
    target_port = domain.target_port or 80
    logger.info(f"Использую порт: {target_port} для домена {domain.name}")
    
    # Если IP или порт не заданы, выводим ошибку
    if not target_ip:
        flash('Не указан целевой IP адрес для FFPanel. Пожалуйста, укажите FFPanel Target IP или Target IP.', 'danger')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Создаем экземпляр FFPanel API с указанным токеном и настроенным логированием
    ffpanel = FFPanelAPI(token=ffpanel_token, logger=logger)
    
    logger.info(f"Создан экземпляр FFPanel API с токеном длиной {len(ffpanel_token)} символов")
    logger.info(f"Базовый URL API: {ffpanel.API_URL}")
    
    # Проверяем подключение к FFPanel и аутентифицируемся
    try:
        if not ffpanel._authenticate():
            logger.error("Ошибка аутентификации в FFPanel API. Проверьте токен и соединение.")
            flash('Ошибка аутентификации в FFPanel API. Проверьте токен и соединение.', 'danger')
            return redirect(url_for('domains.edit', domain_id=domain_id))
        
        logger.info(f"Успешная аутентификация в FFPanel API. Получен JWT токен длиной {len(ffpanel.jwt_token)} символов")
        logger.info(f"Срок действия JWT токена: {ffpanel.jwt_expires}")
    except Exception as auth_error:
        logger.exception(f"Исключение при аутентификации в FFPanel API: {str(auth_error)}")
        flash(f'Ошибка аутентификации в FFPanel API: {str(auth_error)}', 'danger')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Получаем список сайтов из FFPanel с дополнительным логированием
    try:
        sites = ffpanel.get_sites()
        if sites is None:  # Проверяем именно на None, так как может быть пустой список
            logger.error("Не удалось получить список сайтов из FFPanel")
            flash('Ошибка получения списка сайтов из FFPanel', 'danger')
            return redirect(url_for('domains.edit', domain_id=domain_id))
        
        if isinstance(sites, list):
            logger.info(f"Успешно получен список из {len(sites)} сайтов из FFPanel")
        else:
            logger.error(f"Получен неверный формат данных от FFPanel: {type(sites)}")
            flash('Ошибка получения списка сайтов из FFPanel: неверный формат данных', 'danger')
            return redirect(url_for('domains.edit', domain_id=domain_id))
    except Exception as sites_error:
        logger.exception(f"Исключение при получении списка сайтов из FFPanel: {str(sites_error)}")
        flash(f'Ошибка получения списка сайтов из FFPanel: {str(sites_error)}', 'danger')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    logger.info(f"Получено {len(sites)} сайтов из FFPanel")
    
    # Ищем домен в списке сайтов
    site_exists = False
    site_id = None
    
    for site in sites:
        if site.get('domain') == domain.name:
            site_exists = True
            site_id = site.get('id')
            logger.info(f"Найден существующий сайт в FFPanel с ID: {site_id}")
            break
    
    try:
        # В зависимости от того, существует ли сайт, добавляем или обновляем его
        if site_exists and site_id:
            # Собираем данные для обновления сайта
            update_data = {
                'site_id': site_id,
                'ip_path': target_ip,
                'port': str(target_port),
                'port_out': str(target_port),
                'port_ssl': "443",
                'port_out_ssl': "443",
                'real_ip': target_ip,
                'wildcard': "0"
            }
            
            # Обновляем существующий сайт
            logger.info(f"Обновляю существующий сайт {domain.name} (ID: {site_id}) в FFPanel с данными: {update_data}")
            result = ffpanel.update_site(**update_data)
            
            if result.get('success'):
                logger.info(f"Домен {domain.name} успешно обновлен в FFPanel")
                flash(f'Домен {domain.name} успешно обновлен в FFPanel API', 'success')
            else:
                error_msg = result.get('message', 'Неизвестная ошибка')
                logger.error(f"Ошибка обновления домена в FFPanel: {error_msg}")
                flash(f'Ошибка обновления домена в FFPanel API: {error_msg}', 'danger')
        else:
            # Добавляем новый сайт
            add_data = {
                'domain': domain.name,
                'ip_path': target_ip,
                'port': str(target_port),
                'port_out': str(target_port),
                'dns': ""
            }
            
            logger.info(f"Добавляю новый сайт {domain.name} в FFPanel с данными: {add_data}")
            result = ffpanel.add_site(**add_data)
            
            if result.get('success'):
                logger.info(f"Домен {domain.name} успешно добавлен в FFPanel с ID: {result.get('id')}")
                flash(f'Домен {domain.name} успешно добавлен в FFPanel API', 'success')
            else:
                error_msg = result.get('message', 'Неизвестная ошибка')
                logger.error(f"Ошибка добавления домена в FFPanel: {error_msg}")
                flash(f'Ошибка добавления домена в FFPanel API: {error_msg}', 'danger')
    except Exception as e:
        logger.exception(f"Исключение при синхронизации домена с FFPanel: {str(e)}")
        flash(f'Ошибка при синхронизации с FFPanel: {str(e)}', 'danger')
    
    return redirect(url_for('domains.edit', domain_id=domain_id))

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

@bp.route('/<int:domain_id>/deploy_config', methods=['GET', 'POST'])
@login_required
def deploy_domain_config(domain_id):
    """Развертывание конфигурации только для одного домена."""
    from models import Server, ServerLog, DomainGroup
    from flask import current_app
    from modules.domain_manager import DomainManager
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Начало развертывания конфигурации для домена {domain_id}")
    
    domain = Domain.query.get_or_404(domain_id)
    
    # Найдем группы доменов, в которые входит этот домен
    domain_groups = [group for group in domain.groups if group.server_id is not None]
    
    if not domain_groups:
        flash('Домен не привязан к серверу через группу доменов', 'danger')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Берем первый сервер из группы доменов
    server_id = domain_groups[0].server_id
    server = Server.query.get(server_id)
    
    if not server:
        flash('Сервер не найден', 'danger')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Проверяем соединение с сервером
    from modules.server_manager import ServerManager
    logger.info(f"Проверка соединения с сервером {server.name} ({server.ip_address})")
    
    if not ServerManager.check_connectivity(server):
        flash(f'Не удалось подключиться к серверу {server.name}', 'danger')
        return redirect(url_for('domains.edit', domain_id=domain_id))
    
    # Создаем лог операции
    log = ServerLog(
        server_id=server.id,
        action='domain_proxy_deployment',
        status='pending',
        message=f'Запуск деплоя конфигурации прокси для домена {domain.name}'
    )
    db.session.add(log)
    db.session.commit()
    
    try:
        # Разворачиваем конфигурацию для домена
        from modules.proxy_manager import ProxyManager
        logger.info(f"Запуск деплоя конфигурации для домена {domain.name} на сервере {server.name}")
        
        proxy_manager = ProxyManager(current_app.config.get('NGINX_TEMPLATES_PATH', 'templates/nginx'))
        success = proxy_manager.deploy_proxy_config(server.id, domain.id)
        
        if success:
            # Обновляем статус лога
            log.status = 'success'
            log.message = f'Конфигурация прокси для домена {domain.name} успешно развернута'
            db.session.commit()
            
            logger.info(f"Деплой конфигурации для домена {domain.name} выполнен успешно")
            flash(f'Конфигурация для домена {domain.name} успешно развернута', 'success')
        else:
            # Обновляем статус лога в случае ошибки
            log.status = 'error'
            log.message = f'Ошибка при развертывании конфигурации для домена {domain.name}'
            db.session.commit()
            
            logger.error(f"Ошибка при деплое конфигурации для домена {domain.name}")
            flash(f'Ошибка при развертывании конфигурации для домена {domain.name}', 'danger')
            
    except Exception as e:
        # Обновляем статус лога в случае исключения
        log.status = 'error'
        log.message = f'Исключение при развертывании конфигурации для домена {domain.name}: {str(e)}'
        db.session.commit()
        
        logger.exception(f"Исключение при деплое конфигурации для домена {domain.name}")
        flash(f'Ошибка: {str(e)}', 'danger')
    
    return redirect(url_for('domains.edit', domain_id=domain_id))

@bp.route('/ffpanel/import', methods=['GET', 'POST'])
@login_required
def ffpanel_import():
    """Импорт доменов из FFPanel."""
    
    # Проверяем, установлен ли токен FFPanel (в настройках системы или переменных окружения)
    from models import SystemSetting
    
    # Пытаемся получить токен из настроек системы
    ffpanel_token = SystemSetting.get_value('ffpanel_token')
    
    # Если в настройках нет, проверяем переменные окружения
    if not ffpanel_token:
        ffpanel_token = os.environ.get('FFPANEL_TOKEN')
        
    # Если токен не найден нигде, выводим сообщение об ошибке    
    if not ffpanel_token:
        flash('Не настроен токен FFPanel API. Пожалуйста, добавьте токен в настройках системы или переменной окружения FFPANEL_TOKEN.', 'danger')
        return redirect(url_for('settings.index'))
    
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
