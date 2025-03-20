import logging
import asyncio
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash, current_app
from flask_login import login_required
from models import Server, Domain, ServerMetric, DomainMetric, DomainGroup, ServerLog, ServerGroup
from modules.monitoring import MonitoringManager
from modules.domain_manager import DomainManager
from modules.telegram_notifier import TelegramNotifier
from sqlalchemy import func, desc
from app import db

bp = Blueprint('monitoring', __name__, url_prefix='/monitoring')
logger = logging.getLogger(__name__)

@bp.route('/', methods=['GET'])
@login_required
def index():
    """Show monitoring dashboard."""
    # Получаем параметры группы из запроса
    group_id = request.args.get('group_id', type=int)
    server_group_id = request.args.get('server_group_id', type=int)
    
    # Получаем все группы доменов и серверов для фильтра
    domain_groups = DomainGroup.query.all()
    server_groups = ServerGroup.query.order_by(ServerGroup.name).all()
    
    # Фильтруем серверы по группе, если указана
    if server_group_id:
        server_group = ServerGroup.query.get_or_404(server_group_id)
        servers = server_group.servers.all()
    else:
        servers = Server.query.all()
    
    # Фильтруем домены по группе, если указана
    if group_id:
        group = DomainGroup.query.get_or_404(group_id)
        domains = group.domains.all()
    else:
        domains = Domain.query.all()
    
    # Проверяем, настроены ли Telegram-уведомления
    telegram_configured = TelegramNotifier.is_configured()
    
    # Добавляем информацию о группах серверов для дашборда
    server_group_info = {}
    for group in server_groups:
        active_count = sum(1 for s in group.servers if s.status == 'active')
        total_count = group.servers.count()
        server_group_info[group.id] = {
            'name': group.name,
            'active': active_count,
            'total': total_count
        }
    
    return render_template('monitoring/index.html', 
                           servers=servers, 
                           domains=domains,
                           domain_groups=domain_groups,
                           server_groups=server_groups,
                           server_group_info=server_group_info,
                           selected_group_id=group_id,
                           selected_server_group_id=server_group_id,
                           telegram_configured=telegram_configured)

@bp.route('/collect/<int:server_id>', methods=['POST'])
@login_required
def collect_server_metrics(server_id):
    """Manually trigger collection of server metrics."""
    server = Server.query.get_or_404(server_id)
    
    try:
        metric = MonitoringManager.collect_server_metrics(server)
        
        if metric:
            flash(f'Successfully collected metrics for server {server.name}', 'success')
        else:
            flash(f'Failed to collect metrics for server {server.name}', 'danger')
            
    except Exception as e:
        logger.exception(f"Error collecting metrics for server {server.name}")
        flash(f'Error collecting metrics: {str(e)}', 'danger')
    
    return redirect(url_for('monitoring.server_metrics', server_id=server_id))

@bp.route('/server/<int:server_id>', methods=['GET'])
@login_required
def server_metrics(server_id):
    """Show server metrics."""
    server = Server.query.get_or_404(server_id)
    period = request.args.get('period', 'day')
    
    metrics = MonitoringManager.get_server_metrics(server_id, period)
    
    # Format metrics for the chart
    timestamps = [m.timestamp.strftime('%Y-%m-%d %H:%M') for m in metrics]
    cpu_data = [m.cpu_usage for m in metrics]
    memory_data = [m.memory_usage for m in metrics]
    disk_data = [m.disk_usage for m in metrics]
    
    # Get latest metrics
    latest_metric = metrics[-1] if metrics else None
    
    return render_template('monitoring/server.html',
                           server=server,
                           period=period,
                           metrics=metrics,
                           latest_metric=latest_metric,
                           timestamps=timestamps,
                           cpu_data=cpu_data,
                           memory_data=memory_data,
                           disk_data=disk_data)

@bp.route('/domain/<int:domain_id>', methods=['GET'])
@login_required
def domain_metrics(domain_id):
    """Show domain metrics."""
    domain = Domain.query.get_or_404(domain_id)
    period = request.args.get('period', 'day')
    
    metrics = MonitoringManager.get_domain_metrics(domain_id, period)
    aggregates = MonitoringManager.get_domain_aggregate_metrics(domain_id, period)
    
    # Format metrics for the chart
    timestamps = [m.timestamp.strftime('%Y-%m-%d %H:%M') for m in metrics]
    requests_data = [m.requests_count for m in metrics]
    # Показываем только реальное использование полосы пропускания
    bandwidth_data = [(m.bandwidth_used / (1024 * 1024)) if m.bandwidth_used > 0 else 0 for m in metrics]  # Convert to MB
    # Преобразуем None в 0 для графика, чтобы не отображать фиктивные данные
    response_time_data = [m.avg_response_time if m.avg_response_time and m.requests_count > 0 else 0 for m in metrics]
    
    # Get associated server through domain groups
    server = None
    for group in domain.groups:
        if group.server:
            server = group.server
            break
    
    return render_template('monitoring/domain.html',
                           domain=domain,
                           server=server,
                           period=period,
                           metrics=metrics,
                           aggregates=aggregates,
                           timestamps=timestamps,
                           requests_data=requests_data,
                           bandwidth_data=bandwidth_data,
                           response_time_data=response_time_data)

@bp.route('/api/server/<int:server_id>', methods=['GET'])
@login_required
def api_server_metrics(server_id):
    """API endpoint for server metrics data."""
    period = request.args.get('period', 'day')
    metrics = MonitoringManager.get_server_metrics(server_id, period)
    
    data = {
        'timestamps': [m.timestamp.strftime('%Y-%m-%d %H:%M:%S') for m in metrics],
        'cpu': [m.cpu_usage for m in metrics],
        'memory': [m.memory_usage for m in metrics],
        'disk': [m.disk_usage for m in metrics],
        'load': [m.load_average for m in metrics]
    }
    
    return jsonify(data)

@bp.route('/api/domain/<int:domain_id>', methods=['GET'])
@login_required
def api_domain_metrics(domain_id):
    """API endpoint for domain metrics data."""
    period = request.args.get('period', 'day')
    metrics = MonitoringManager.get_domain_metrics(domain_id, period)
    
    data = {
        'timestamps': [m.timestamp.strftime('%Y-%m-%d %H:%M:%S') for m in metrics],
        'requests': [m.requests_count for m in metrics],
        'bandwidth': [(m.bandwidth_used / (1024 * 1024)) if m.bandwidth_used > 0 else 0 for m in metrics],  # Convert to MB
        'response_time': [m.avg_response_time if m.avg_response_time and m.requests_count > 0 else 0 for m in metrics],
        'status_2xx': [m.status_2xx_count for m in metrics],
        'status_3xx': [m.status_3xx_count for m in metrics],
        'status_4xx': [m.status_4xx_count for m in metrics],
        'status_5xx': [m.status_5xx_count for m in metrics]
    }
    
    return jsonify(data)

@bp.route('/collect/domain/<int:domain_id>', methods=['POST'])
@login_required
def collect_domain_metrics(domain_id):
    """Manually trigger collection of domain metrics."""
    domain = Domain.query.get_or_404(domain_id)
    
    # Find associated server
    server = None
    for group in domain.groups:
        if group.server:
            server = group.server
            break
    
    if not server:
        flash(f'Cannot collect metrics: Domain {domain.name} is not associated with any server', 'danger')
        return redirect(url_for('monitoring.domain_metrics', domain_id=domain_id))
    
    try:
        metric = MonitoringManager.collect_domain_metrics(server, domain)
        
        if metric:
            flash(f'Successfully collected metrics for domain {domain.name}', 'success')
        else:
            flash(f'Failed to collect metrics for domain {domain.name}', 'danger')
            
    except Exception as e:
        logger.exception(f"Error collecting metrics for domain {domain.name}")
        flash(f'Error collecting metrics: {str(e)}', 'danger')
    
    return redirect(url_for('monitoring.domain_metrics', domain_id=domain_id))


@bp.route('/send-report', methods=['POST'])
@login_required
def send_daily_report():
    """Отправляет ежедневный отчет вручную."""
    # Проверяем, настроены ли Telegram уведомления
    if not TelegramNotifier.is_configured():
        flash('Telegram notifications are not configured', 'danger')
        return redirect(url_for('monitoring.index'))
    
    try:
        # Создаем и запускаем новый event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Отправляем отчет
            loop.run_until_complete(TelegramNotifier.send_daily_report())
            flash('Daily report has been sent successfully', 'success')
            
            # Записываем в лог
            logger.info("Daily report sent manually by user")
        finally:
            loop.close()
            
    except Exception as e:
        logger.exception("Error sending daily report manually")
        flash(f'Error sending report: {str(e)}', 'danger')
    
    # Перенаправляем обратно на страницу мониторинга
    return redirect(url_for('monitoring.index'))

@bp.route('/activity-logs', methods=['GET'])
@login_required
def activity_logs():
    """Show activity logs page with detailed system logs."""
    # Получаем параметры фильтрации из GET запроса
    server_id = request.args.get('server_id', type=int)
    action = request.args.get('action')
    status = request.args.get('status')
    date_range = request.args.get('date_range', '30')
    page = request.args.get('page', 1, type=int)
    per_page = 50  # количество записей на странице
    
    # Базовый запрос для получения логов
    query = ServerLog.query
    
    # Применяем фильтры
    if server_id:
        query = query.filter(ServerLog.server_id == server_id)
    if action:
        query = query.filter(ServerLog.action == action)
    if status:
        query = query.filter(ServerLog.status == status)
    
    # Фильтр по дате
    if date_range != 'all':
        try:
            days = int(date_range)
            date_from = datetime.utcnow() - timedelta(days=days)
            query = query.filter(ServerLog.created_at >= date_from)
        except (ValueError, TypeError):
            # Если произошла ошибка при конвертации, просто игнорируем фильтр по дате
            pass
    
    # Сортировка по дате (самые новые сверху)
    query = query.order_by(desc(ServerLog.created_at))
    
    # Получаем все доступные действия для фильтра
    actions = db.session.query(ServerLog.action).distinct().all()
    actions = [a[0] for a in actions]
    
    # Получаем все сервера для фильтра
    servers = Server.query.all()
    
    # Получаем общее количество записей и статистику
    total_logs = query.count()
    
    # Получаем статистику по статусам
    success_count = query.filter(ServerLog.status == 'success').count()
    pending_count = query.filter(ServerLog.status == 'pending').count()
    error_count = query.filter(ServerLog.status == 'error').count()
    
    # Статистика для самых частых действий
    top_actions_query = db.session.query(
        ServerLog.action, 
        func.count(ServerLog.id).label('count')
    ).group_by(ServerLog.action).order_by(desc('count')).limit(5).all()
    
    # Настраиваем пагинацию
    total_pages = (total_logs + per_page - 1) // per_page  # округление вверх
    offset = (page - 1) * per_page
    logs = query.limit(per_page).offset(offset).all()
    
    # Собираем статистику для отображения
    stats = {
        'total': total_logs,
        'success': success_count,
        'pending': pending_count,
        'error': error_count
    }
    
    pagination = {
        'page': page,
        'per_page': per_page,
        'pages': total_pages,
        'total': total_logs
    }
    
    return render_template(
        'monitoring/activity_logs.html',
        logs=logs,
        servers=servers,
        actions=actions,
        stats=stats,
        top_actions=top_actions_query,
        pagination=pagination
    )