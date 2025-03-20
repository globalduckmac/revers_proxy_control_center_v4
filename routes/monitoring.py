import logging
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash, current_app
from flask_login import login_required
from models import Server, Domain, ServerMetric, DomainMetric
from modules.monitoring import MonitoringManager
from modules.domain_manager import DomainManager

bp = Blueprint('monitoring', __name__, url_prefix='/monitoring')
logger = logging.getLogger(__name__)

@bp.route('/', methods=['GET'])
@login_required
def index():
    """Show monitoring dashboard."""
    servers = Server.query.all()
    domains = Domain.query.all()
    
    return render_template('monitoring/index.html', 
                           servers=servers, 
                           domains=domains)

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