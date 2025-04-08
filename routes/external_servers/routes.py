from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required
import json
import datetime
import requests
from sqlalchemy import desc

from app import db
from models import ExternalServer, ExternalServerMetric, Server

bp = Blueprint('external_servers', __name__, url_prefix='/external-servers')


@bp.route('/')
@login_required
def index():
    """Отображает список всех внешних серверов."""
    servers = []
    
    # Получаем записи из таблицы external_servers (новый формат)
    new_servers = ExternalServer.query.order_by(ExternalServer.name).all()
    servers.extend(new_servers)
    
    # Получаем записи из таблицы external_server (старый формат, если есть)
    try:
        # Создаем динамический класс для таблицы external_server
        class OldExternalServer(db.Model):
            __tablename__ = 'external_server'
            __table_args__ = {'extend_existing': True}
            
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(64))
            ip_address = db.Column(db.String(45))
            description = db.Column(db.Text)
            is_active = db.Column(db.Boolean)
            created_at = db.Column(db.DateTime)
            updated_at = db.Column(db.DateTime)
            last_check = db.Column(db.DateTime)
            last_status = db.Column(db.String(32))
            glances_port = db.Column(db.Integer)
        
        old_servers = OldExternalServer.query.order_by(OldExternalServer.name).all()
        if old_servers:
            print(f"Found {len(old_servers)} servers in old table format")
            servers.extend(old_servers)
    except Exception as e:
        print(f"Error getting old servers: {e}")
    
    return render_template('external_servers/index.html', servers=servers)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создает новый внешний сервер."""
    if request.method == 'POST':
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        description = request.form.get('description')
        location = request.form.get('location')
        glances_port = request.form.get('glances_port', 61208, type=int)
        glances_api_user = request.form.get('glances_api_user')
        glances_api_password = request.form.get('glances_api_password')
        
        # Проверка обязательных полей
        if not name or not ip_address:
            flash('Имя и IP-адрес являются обязательными полями.', 'danger')
            return render_template('external_servers/create.html')
        
        # Создание нового сервера
        server = ExternalServer(
            name=name,
            ip_address=ip_address,
            description=description,
            location=location,
            glances_port=glances_port,
            glances_api_user=glances_api_user,
            glances_api_password=glances_api_password,
            is_active=True
        )
        
        try:
            db.session.add(server)
            db.session.commit()
            flash(f'Внешний сервер "{name}" успешно создан.', 'success')
            return redirect(url_for('external_servers.view', server_id=server.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при создании сервера: {str(e)}', 'danger')
    
    return render_template('external_servers/create.html')


@bp.route('/<int:server_id>', methods=['GET'])
@login_required
def view(server_id):
    """Отображает информацию о внешнем сервере."""
    server = ExternalServer.query.get_or_404(server_id)
    metrics = ExternalServerMetric.query.filter_by(server_id=server_id).order_by(
        desc(ExternalServerMetric.timestamp)).limit(100).all()
    
    return render_template('external_servers/view.html', server=server, metrics=metrics)


@bp.route('/<int:server_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(server_id):
    """Редактирует информацию о внешнем сервере."""
    server = ExternalServer.query.get_or_404(server_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        description = request.form.get('description')
        location = request.form.get('location')
        glances_port = request.form.get('glances_port', 61208, type=int)
        glances_api_user = request.form.get('glances_api_user')
        glances_api_password = request.form.get('glances_api_password')
        is_active = 'is_active' in request.form
        
        # Проверка обязательных полей
        if not name or not ip_address:
            flash('Имя и IP-адрес являются обязательными полями.', 'danger')
            return render_template('external_servers/edit.html', server=server)
        
        # Обновление данных сервера
        server.name = name
        server.ip_address = ip_address
        server.description = description
        server.location = location
        server.glances_port = glances_port
        server.glances_api_user = glances_api_user
        # Обновляем пароль только если он был указан
        if glances_api_password:
            server.glances_api_password = glances_api_password
        server.is_active = is_active
        
        try:
            db.session.commit()
            flash(f'Внешний сервер "{name}" успешно обновлен.', 'success')
            return redirect(url_for('external_servers.view', server_id=server.id))
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
        # Удаляем все связанные метрики (на всякий случай, хотя cascade должен сработать)
        ExternalServerMetric.query.filter_by(server_id=server_id).delete()
        
        # Удаляем сервер
        db.session.delete(server)
        db.session.commit()
        
        flash(f'Внешний сервер "{server.name}" и все его метрики успешно удалены.', 'success')
        return redirect(url_for('external_servers.index'))
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении сервера: {str(e)}', 'danger')
        return redirect(url_for('external_servers.view', server_id=server_id))


@bp.route('/<int:server_id>/check', methods=['POST'])
@login_required
def check(server_id):
    """Выполняет проверку внешнего сервера и сбор метрик."""
    server = ExternalServer.query.get_or_404(server_id)
    
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
        server.last_check_time = datetime.datetime.utcnow()
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
        
        flash(f'Метрики сервера "{server.name}" успешно обновлены.', 'success')
    except Exception as e:
        db.session.rollback()
        server.last_check_time = datetime.datetime.utcnow()
        server.last_status = 'error'
        db.session.commit()
        
        flash(f'Ошибка при проверке сервера: {str(e)}', 'danger')
    
    return redirect(url_for('external_servers.view', server_id=server_id))


@bp.route('/<int:server_id>/metrics', methods=['GET'])
@login_required
def get_metrics_json(server_id):
    """Возвращает метрики сервера в формате JSON для построения графиков."""
    server = ExternalServer.query.get_or_404(server_id)
    period = request.args.get('period', '24h')
    
    # Определяем временной интервал
    now = datetime.datetime.utcnow()
    if period == '24h':
        start_time = now - datetime.timedelta(hours=24)
    elif period == '7d':
        start_time = now - datetime.timedelta(days=7)
    elif period == '30d':
        start_time = now - datetime.timedelta(days=30)
    else:
        start_time = now - datetime.timedelta(hours=24)
    
    # Получаем метрики из базы данных
    metrics = ExternalServerMetric.query.filter_by(server_id=server_id) \
        .filter(ExternalServerMetric.timestamp >= start_time) \
        .order_by(ExternalServerMetric.timestamp) \
        .all()
    
    # Форматируем данные для графиков
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