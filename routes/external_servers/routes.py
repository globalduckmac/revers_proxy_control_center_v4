from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from models import ExternalServer, ExternalServerMetric
import logging
import json
from datetime import datetime, timedelta
import requests

bp = Blueprint('external_servers', __name__, url_prefix='/external-servers')
logger = logging.getLogger(__name__)

@bp.route('/')
@login_required
def index():
    """Отображает список внешних серверов."""
    servers = ExternalServer.query.all()
    return render_template('external_servers/index.html', servers=servers)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создает новый внешний сервер."""
    if request.method == 'POST':
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        description = request.form.get('description')
        glances_port = request.form.get('glances_port', 61208, type=int)
        glances_api_user = request.form.get('glances_api_user')
        glances_api_password = request.form.get('glances_api_password')
        location = request.form.get('location')
        
        # Проверка обязательных полей
        if not name or not ip_address:
            flash('Имя и IP-адрес обязательны для заполнения', 'danger')
            return render_template('external_servers/create.html')
        
        # Создание нового сервера
        server = ExternalServer(
            name=name,
            ip_address=ip_address,
            description=description,
            glances_port=glances_port,
            glances_api_user=glances_api_user,
            glances_api_password=glances_api_password,
            location=location,
            is_active=True
        )
        
        db.session.add(server)
        
        try:
            db.session.commit()
            flash(f'Внешний сервер {name} успешно добавлен', 'success')
            
            # Проверяем доступность Glances API
            try:
                check_glances_availability(server)
            except Exception as e:
                logger.error(f"Ошибка при проверке доступности Glances API: {e}")
                flash(f'Сервер добавлен, но Glances API не отвечает: {str(e)}', 'warning')
            
            return redirect(url_for('external_servers.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении сервера: {str(e)}', 'danger')
    
    return render_template('external_servers/create.html')

@bp.route('/<int:server_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(server_id):
    """Редактирует существующий внешний сервер."""
    server = ExternalServer.query.get_or_404(server_id)
    
    if request.method == 'POST':
        server.name = request.form.get('name')
        server.ip_address = request.form.get('ip_address')
        server.description = request.form.get('description')
        server.glances_port = request.form.get('glances_port', 61208, type=int)
        server.glances_api_user = request.form.get('glances_api_user')
        server.glances_api_password = request.form.get('glances_api_password')
        server.location = request.form.get('location')
        server.is_active = 'is_active' in request.form
        
        try:
            db.session.commit()
            flash(f'Внешний сервер {server.name} успешно обновлен', 'success')
            
            # Проверяем доступность Glances API
            try:
                check_glances_availability(server)
            except Exception as e:
                logger.error(f"Ошибка при проверке доступности Glances API: {e}")
                flash(f'Сервер обновлен, но Glances API не отвечает: {str(e)}', 'warning')
            
            return redirect(url_for('external_servers.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении сервера: {str(e)}', 'danger')
    
    return render_template('external_servers/edit.html', server=server)

@bp.route('/<int:server_id>/delete', methods=['POST'])
@login_required
def delete(server_id):
    """Удаляет внешний сервер."""
    server = ExternalServer.query.get_or_404(server_id)
    
    try:
        db.session.delete(server)
        db.session.commit()
        flash(f'Внешний сервер {server.name} успешно удален', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении сервера: {str(e)}', 'danger')
    
    return redirect(url_for('external_servers.index'))

@bp.route('/<int:server_id>/view')
@login_required
def view(server_id):
    """Просмотр подробной информации о внешнем сервере."""
    server = ExternalServer.query.get_or_404(server_id)
    
    # Получаем метрики сервера за последние 24 часа
    yesterday = datetime.utcnow() - timedelta(days=1)
    metrics = ExternalServerMetric.query.filter(
        ExternalServerMetric.server_id == server_id,
        ExternalServerMetric.timestamp >= yesterday
    ).order_by(ExternalServerMetric.timestamp.desc()).all()
    
    return render_template('external_servers/view.html', server=server, metrics=metrics)

@bp.route('/<int:server_id>/check', methods=['POST'])
@login_required
def check(server_id):
    """Проверяет доступность внешнего сервера и собирает текущие метрики."""
    server = ExternalServer.query.get_or_404(server_id)
    
    try:
        # Проверяем доступность Glances и собираем метрики
        metrics = collect_server_metrics(server)
        
        if metrics:
            flash(f'Сервер {server.name} доступен, метрики успешно собраны', 'success')
        else:
            flash(f'Не удалось собрать метрики сервера {server.name}', 'warning')
    
    except Exception as e:
        logger.exception(f"Ошибка при проверке сервера {server.name}: {e}")
        flash(f'Ошибка при проверке сервера: {str(e)}', 'danger')
    
    return redirect(url_for('external_servers.view', server_id=server_id))

@bp.route('/<int:server_id>/metrics/json')
@login_required
def get_metrics_json(server_id):
    """Возвращает метрики сервера в формате JSON для графиков."""
    server = ExternalServer.query.get_or_404(server_id)
    
    # Получаем период из параметров запроса или используем 24 часа по умолчанию
    period = request.args.get('period', '24h')
    
    if period == '24h':
        start_time = datetime.utcnow() - timedelta(hours=24)
    elif period == '7d':
        start_time = datetime.utcnow() - timedelta(days=7)
    elif period == '30d':
        start_time = datetime.utcnow() - timedelta(days=30)
    else:
        start_time = datetime.utcnow() - timedelta(hours=24)
    
    # Получаем метрики за указанный период
    metrics = ExternalServerMetric.query.filter(
        ExternalServerMetric.server_id == server_id,
        ExternalServerMetric.timestamp >= start_time
    ).order_by(ExternalServerMetric.timestamp.asc()).all()
    
    # Формируем данные для графиков
    timestamps = [metric.timestamp.strftime('%Y-%m-%d %H:%M:%S') for metric in metrics]
    cpu_data = [metric.cpu_percent for metric in metrics]
    memory_data = [metric.memory_percent for metric in metrics]
    disk_data = [metric.disk_percent for metric in metrics]
    load_avg_1_data = [metric.load_avg_1 for metric in metrics]
    load_avg_5_data = [metric.load_avg_5 for metric in metrics]
    load_avg_15_data = [metric.load_avg_15 for metric in metrics]
    
    return jsonify({
        'timestamps': timestamps,
        'cpu': cpu_data,
        'memory': memory_data,
        'disk': disk_data,
        'load_avg_1': load_avg_1_data,
        'load_avg_5': load_avg_5_data,
        'load_avg_15': load_avg_15_data
    })

def check_glances_availability(server):
    """
    Проверяет доступность Glances API.
    
    Args:
        server: объект ExternalServer
        
    Returns:
        bool: True если Glances API доступен, иначе вызывает исключение
    """
    url = f"http://{server.ip_address}:{server.glances_port}/api/3/cpu"
    
    # Настройка аутентификации, если указаны учетные данные
    auth = None
    if server.glances_api_user and server.glances_api_password:
        auth = (server.glances_api_user, server.glances_api_password)
    
    response = requests.get(url, auth=auth, timeout=5)
    response.raise_for_status()
    
    return True

def collect_server_metrics(server):
    """
    Собирает метрики сервера через Glances API.
    
    Args:
        server: объект ExternalServer
        
    Returns:
        ExternalServerMetric: созданный объект метрики или None в случае ошибки
    """
    try:
        # Базовый URL для Glances API
        base_url = f"http://{server.ip_address}:{server.glances_port}/api/3"
        
        # Настройка аутентификации, если указаны учетные данные
        auth = None
        if server.glances_api_user and server.glances_api_password:
            auth = (server.glances_api_user, server.glances_api_password)
        
        # Получаем данные о различных метриках
        cpu_info = requests.get(f"{base_url}/cpu", auth=auth, timeout=5).json()
        memory_info = requests.get(f"{base_url}/mem", auth=auth, timeout=5).json()
        disk_info = requests.get(f"{base_url}/fs", auth=auth, timeout=5).json()
        load_info = requests.get(f"{base_url}/load", auth=auth, timeout=5).json()
        process_info = requests.get(f"{base_url}/processcount", auth=auth, timeout=5).json()
        network_info = requests.get(f"{base_url}/network", auth=auth, timeout=5).json()
        
        # Извлекаем нужные значения из ответов
        cpu_percent = cpu_info.get('total', 0)
        memory_percent = memory_info.get('percent', 0)
        
        # Вычисляем среднее использование дисков
        disk_percent = 0
        if disk_info:
            disk_percents = [fs.get('percent', 0) for fs in disk_info if fs.get('mnt_point') == '/']
            if disk_percents:
                disk_percent = disk_percents[0]
        
        # Получаем load average
        load_avg_1 = load_info.get('min1', 0)
        load_avg_5 = load_info.get('min5', 0)
        load_avg_15 = load_info.get('min15', 0)
        
        # Информация о процессах
        processes_total = process_info.get('total', 0)
        processes_running = process_info.get('running', 0)
        
        # Информация о сети
        network_in_bytes = 0
        network_out_bytes = 0
        if network_info:
            for interface in network_info:
                if interface.get('interface_name') not in ('lo', 'localhost'):
                    network_in_bytes += interface.get('cumulative_rx', 0)
                    network_out_bytes += interface.get('cumulative_tx', 0)
        
        # Определяем статус сервера на основе метрик
        status = 'ok'
        if cpu_percent > 80 or memory_percent > 80 or disk_percent > 80:
            status = 'warning'
        if cpu_percent > 95 or memory_percent > 95 or disk_percent > 95:
            status = 'error'
        
        # Сохраняем последние метрики в модели сервера
        server.last_check_time = datetime.utcnow()
        server.last_status = status
        server.cpu_percent = cpu_percent
        server.memory_percent = memory_percent
        server.disk_percent = disk_percent
        server.load_avg_1 = load_avg_1
        server.load_avg_5 = load_avg_5
        server.load_avg_15 = load_avg_15
        
        # Создаем запись метрики
        metric = ExternalServerMetric(
            server_id=server.id,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_percent=disk_percent,
            load_avg_1=load_avg_1,
            load_avg_5=load_avg_5,
            load_avg_15=load_avg_15,
            processes_total=processes_total,
            processes_running=processes_running,
            network_in_bytes=network_in_bytes,
            network_out_bytes=network_out_bytes,
            metrics_data=json.dumps({
                'cpu': cpu_info,
                'memory': memory_info,
                'disk': disk_info,
                'load': load_info,
                'processes': process_info,
                'network': network_info
            })
        )
        
        db.session.add(metric)
        db.session.commit()
        
        return metric
        
    except Exception as e:
        logger.exception(f"Ошибка при сборе метрик для сервера {server.name}: {e}")
        
        # Обновляем статус сервера на ошибку
        server.last_check_time = datetime.utcnow()
        server.last_status = 'error'
        db.session.commit()
        
        raise