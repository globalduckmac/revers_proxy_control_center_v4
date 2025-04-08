import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
import json
from datetime import datetime, timedelta
import requests
import logging
import ipaddress

from app import db
from models import ExternalServer, ExternalServerMetric

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем блюпринт
bp = Blueprint('external_servers', __name__)

@bp.route('/')
@login_required
def index():
    """Отображает список всех внешних серверов."""
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
        glances_enabled = 'glances_enabled' in request.form
        glances_port = request.form.get('glances_port', type=int) or 61208
        
        # Проверка обязательных полей
        if not name or not ip_address:
            flash('Необходимо указать название и IP-адрес сервера', 'danger')
            return render_template('external_servers/create.html')
        
        # Проверка валидности IP-адреса
        try:
            ipaddress.ip_address(ip_address)
        except ValueError:
            flash('Некорректный IP-адрес', 'danger')
            return render_template('external_servers/create.html')
        
        # Проверка уникальности названия и IP-адреса
        if ExternalServer.query.filter_by(name=name).first():
            flash('Сервер с таким названием уже существует', 'danger')
            return render_template('external_servers/create.html')
        
        if ExternalServer.query.filter_by(ip_address=ip_address).first():
            flash('Сервер с таким IP-адресом уже существует', 'danger')
            return render_template('external_servers/create.html')
        
        # Создание нового сервера
        server = ExternalServer(
            name=name,
            ip_address=ip_address,
            description=description,
            glances_enabled=glances_enabled,
            glances_port=glances_port
        )
        
        db.session.add(server)
        db.session.commit()
        
        flash(f'Внешний сервер {name} успешно добавлен', 'success')
        
        # Запускаем первую проверку
        check_server_metrics(server.id)
        
        return redirect(url_for('external_servers.index'))
    
    return render_template('external_servers/create.html')

@bp.route('/<int:server_id>')
@login_required
def view(server_id):
    """Отображает детальную информацию о внешнем сервере."""
    server = ExternalServer.query.get_or_404(server_id)
    
    # Получаем последние метрики
    metrics = ExternalServerMetric.query.filter_by(external_server_id=server_id).order_by(ExternalServerMetric.timestamp.desc()).first()
    
    # Получаем историю метрик за последние 24 часа
    history = ExternalServerMetric.query.filter_by(external_server_id=server_id)\
        .filter(ExternalServerMetric.timestamp >= datetime.utcnow() - timedelta(hours=24))\
        .order_by(ExternalServerMetric.timestamp)\
        .all()
    
    # Готовим данные для графика
    chart_data = {
        'labels': [],
        'cpu': [],
        'memory': [],
        'disk': []
    }
    
    # Отладочная информация о количестве метрик
    logger.info(f"Найдено {len(history)} метрик для сервера {server.name} за последние 24 часа")
    
    for metric in history:
        chart_data['labels'].append(metric.timestamp.strftime('%H:%M'))
        chart_data['cpu'].append(metric.cpu_usage if metric.cpu_usage is not None else 0)
        chart_data['memory'].append(metric.memory_usage if metric.memory_usage is not None else 0)
        chart_data['disk'].append(metric.disk_usage if metric.disk_usage is not None else 0)
    
    # Если данных нет, добавляем фиктивную точку с текущим временем для отображения графика
    if not history and metrics:
        current_time = datetime.utcnow()
        chart_data['labels'].append(current_time.strftime('%H:%M'))
        chart_data['cpu'].append(metrics.cpu_usage if metrics.cpu_usage is not None else 0)
        chart_data['memory'].append(metrics.memory_usage if metrics.memory_usage is not None else 0)
        chart_data['disk'].append(metrics.disk_usage if metrics.disk_usage is not None else 0)
    
    return render_template(
        'external_servers/view.html',
        server=server,
        metrics=metrics,
        chart_data=json.dumps(chart_data)
    )

@bp.route('/<int:server_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(server_id):
    """Редактирует внешний сервер."""
    server = ExternalServer.query.get_or_404(server_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        description = request.form.get('description')
        glances_enabled = 'glances_enabled' in request.form
        glances_port = request.form.get('glances_port', type=int) or 61208
        is_active = 'is_active' in request.form
        
        # Проверка обязательных полей
        if not name or not ip_address:
            flash('Необходимо указать название и IP-адрес сервера', 'danger')
            return render_template('external_servers/edit.html', server=server)
        
        # Проверка валидности IP-адреса
        try:
            ipaddress.ip_address(ip_address)
        except ValueError:
            flash('Некорректный IP-адрес', 'danger')
            return render_template('external_servers/edit.html', server=server)
        
        # Проверка уникальности названия и IP-адреса (исключая текущий сервер)
        if ExternalServer.query.filter(ExternalServer.name == name, ExternalServer.id != server_id).first():
            flash('Сервер с таким названием уже существует', 'danger')
            return render_template('external_servers/edit.html', server=server)
        
        if ExternalServer.query.filter(ExternalServer.ip_address == ip_address, ExternalServer.id != server_id).first():
            flash('Сервер с таким IP-адресом уже существует', 'danger')
            return render_template('external_servers/edit.html', server=server)
        
        # Обновление сервера
        server.name = name
        server.ip_address = ip_address
        server.description = description
        server.glances_enabled = glances_enabled
        server.glances_port = glances_port
        server.is_active = is_active
        
        db.session.commit()
        
        flash(f'Внешний сервер {name} успешно обновлен', 'success')
        return redirect(url_for('external_servers.index'))
    
    return render_template('external_servers/edit.html', server=server)

@bp.route('/<int:server_id>/delete', methods=['POST'])
@login_required
def delete(server_id):
    """Удаляет внешний сервер."""
    server = ExternalServer.query.get_or_404(server_id)
    
    name = server.name
    db.session.delete(server)
    db.session.commit()
    
    flash(f'Внешний сервер {name} успешно удален', 'success')
    return redirect(url_for('external_servers.index'))

@bp.route('/<int:server_id>/check', methods=['POST'])
@login_required
def check_server(server_id):
    """Проверяет доступность внешнего сервера и получает его метрики."""
    server = ExternalServer.query.get_or_404(server_id)
    
    # Выполняем проверку сервера
    result = check_server_metrics(server_id)
    
    if result:
        flash(f'Проверка сервера {server.name} успешно выполнена', 'success')
    else:
        flash(f'Ошибка при проверке сервера {server.name}', 'danger')
    
    return redirect(url_for('external_servers.view', server_id=server_id))

def check_server_metrics(server_id):
    """
    Проверяет доступность внешнего сервера и получает его метрики через Glances API.
    
    Args:
        server_id: ID внешнего сервера
        
    Returns:
        bool: True, если проверка успешна, иначе False
    """
    server = ExternalServer.query.get(server_id)
    if not server:
        logger.error(f"Сервер с ID {server_id} не найден")
        return False
    
    if not server.glances_enabled:
        logger.info(f"Glances не включен для сервера {server.name}")
        server.status = 'unknown'
        server.last_check = datetime.utcnow()
        db.session.commit()
        return False
    
    try:
        # Пытаемся получить метрики через Glances API
        metrics = get_server_metrics_via_glances(server)
        
        # Обновляем статус сервера
        server.status = 'online'
        server.last_check = datetime.utcnow()
        db.session.commit()
        
        # Если метрики получены успешно, сохраняем их
        if metrics:
            new_metric = ExternalServerMetric(
                external_server_id=server.id,
                metric_type='system',
                metric_name='general',
                metric_value='0',  # Устанавливаем значение по умолчанию
                cpu_usage=metrics.get('cpu_usage'),
                memory_usage=metrics.get('memory_usage'),
                disk_usage=metrics.get('disk_usage'),
                load_average=metrics.get('load_average'),
                collection_method='glances_api',
                timestamp=datetime.utcnow()
            )
            db.session.add(new_metric)
            db.session.commit()
            return True
            
        return False
        
    except Exception as e:
        logger.error(f"Ошибка при проверке сервера {server.name}: {str(e)}")
        server.status = 'offline'
        server.last_check = datetime.utcnow()
        db.session.commit()
        return False

def get_server_metrics_via_glances(server):
    """
    Получает метрики сервера через Glances API.
    
    Args:
        server: Объект ExternalServer
        
    Returns:
        dict: Словарь с метриками или None в случае ошибки
    """
    try:
        # Запрос метрик CPU
        cpu_url = f"{server.get_glances_api_url()}/cpu"
        cpu_response = requests.get(cpu_url, timeout=5)
        cpu_data = cpu_response.json()
        
        # Запрос метрик памяти
        mem_url = f"{server.get_glances_api_url()}/mem"
        mem_response = requests.get(mem_url, timeout=5)
        mem_data = mem_response.json()
        
        # Запрос метрик нагрузки
        load_url = f"{server.get_glances_api_url()}/load"
        load_response = requests.get(load_url, timeout=5)
        load_data = load_response.json()
        
        # Запрос метрик дисков
        fs_url = f"{server.get_glances_api_url()}/fs"
        fs_response = requests.get(fs_url, timeout=5)
        fs_data = fs_response.json()
        
        # Вычисляем общее использование CPU
        cpu_usage = round(cpu_data.get('total', 0), 1)
        
        # Вычисляем использование памяти
        memory_total = mem_data.get('total', 0)
        memory_used = mem_data.get('used', 0)
        memory_usage = round((memory_used / memory_total * 100), 1) if memory_total else 0
        
        # Получаем средний показатель нагрузки за 1 минуту
        load_average = load_data.get('min1', 0)
        
        # Вычисляем общее использование диска (берем среднее значение всех дисков)
        disk_usage = 0
        disk_count = 0
        
        for disk in fs_data:
            # Учитываем только диски с процентным заполнением
            if 'percent' in disk:
                disk_usage += disk.get('percent', 0)
                disk_count += 1
        
        # Вычисляем среднее использование дисков
        if disk_count > 0:
            disk_usage = round(disk_usage / disk_count, 1)
        
        return {
            'cpu_usage': cpu_usage,
            'memory_usage': memory_usage,
            'disk_usage': disk_usage,
            'load_average': str(load_average),
            'timestamp': datetime.utcnow()
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к Glances API: {str(e)}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Ошибка при обработке данных от Glances API: {str(e)}")
        return None