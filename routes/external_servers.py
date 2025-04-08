from app import db
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from models import ExternalServer, ExternalServerMetric
import os
import datetime
import logging
import json
import requests

# Создаем Blueprint
bp = Blueprint('external_servers', __name__)

@bp.route('/')
@login_required
def index():
    """Список внешних серверов."""
    servers = ExternalServer.query.all()
    return render_template('external_servers/index.html', servers=servers)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Добавление нового внешнего сервера."""
    if request.method == 'POST':
        # Получаем данные формы
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        description = request.form.get('description')
        glances_enabled = 'glances_enabled' in request.form
        glances_port = request.form.get('glances_port') or 61208  # По умолчанию 61208

        # Проверяем обязательные поля
        if not name or not ip_address:
            flash('Пожалуйста, заполните все обязательные поля', 'danger')
            return render_template('external_servers/create.html')

        # Создаем новый внешний сервер
        server = ExternalServer(
            name=name,
            ip_address=ip_address,
            description=description,
            glances_enabled=glances_enabled,
            glances_port=int(glances_port),
            is_active=True
        )

        # Сохраняем в базу данных
        db.session.add(server)
        db.session.commit()

        flash(f'Внешний сервер {name} успешно добавлен', 'success')
        return redirect(url_for('external_servers.index'))

    # GET запрос: отображаем форму
    return render_template('external_servers/create.html')

@bp.route('/<int:server_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(server_id):
    """Редактирование внешнего сервера."""
    server = ExternalServer.query.get_or_404(server_id)

    if request.method == 'POST':
        # Получаем данные формы
        server.name = request.form.get('name')
        server.ip_address = request.form.get('ip_address')
        server.description = request.form.get('description')
        server.glances_enabled = 'glances_enabled' in request.form
        server.glances_port = int(request.form.get('glances_port') or 61208)
        server.is_active = 'is_active' in request.form

        # Проверяем обязательные поля
        if not server.name or not server.ip_address:
            flash('Пожалуйста, заполните все обязательные поля', 'danger')
            return render_template('external_servers/edit.html', server=server)

        # Сохраняем изменения
        db.session.commit()

        flash(f'Внешний сервер {server.name} успешно обновлен', 'success')
        return redirect(url_for('external_servers.index'))

    # GET запрос: отображаем форму редактирования
    return render_template('external_servers/edit.html', server=server)

@bp.route('/<int:server_id>/delete', methods=['POST'])
@login_required
def delete(server_id):
    """Удаление внешнего сервера."""
    server = ExternalServer.query.get_or_404(server_id)
    server_name = server.name

    # Удаляем сервер
    db.session.delete(server)
    db.session.commit()

    flash(f'Внешний сервер {server_name} успешно удален', 'success')
    return redirect(url_for('external_servers.index'))

@bp.route('/<int:server_id>/view')
@login_required
def view(server_id):
    """Просмотр информации о внешнем сервере."""
    server = ExternalServer.query.get_or_404(server_id)
    
    # Получаем последние метрики для сервера
    metrics = ExternalServerMetric.query.filter_by(external_server_id=server.id)\
        .order_by(ExternalServerMetric.timestamp.desc()).limit(1).first()

    # Получаем историю метрик для графиков
    history_metrics = ExternalServerMetric.query.filter_by(external_server_id=server.id)\
        .order_by(ExternalServerMetric.timestamp.desc()).limit(24).all()
    
    # Форматируем данные для графиков
    chart_data = {
        'labels': [],
        'cpu': [],
        'memory': [],
        'disk': []
    }
    
    for metric in reversed(history_metrics):
        chart_data['labels'].append(metric.timestamp.strftime('%H:%M'))
        chart_data['cpu'].append(metric.cpu_usage or 0)
        chart_data['memory'].append(metric.memory_usage or 0)
        chart_data['disk'].append(metric.disk_usage or 0)
    
    return render_template('external_servers/view.html', 
                           server=server, 
                           metrics=metrics,
                           chart_data=json.dumps(chart_data))

@bp.route('/<int:server_id>/check', methods=['POST'])
@login_required
def check_server(server_id):
    """Проверка доступности внешнего сервера."""
    from modules.monitoring import get_server_metrics_via_glances
    
    server = ExternalServer.query.get_or_404(server_id)
    logger = current_app.logger
    
    try:
        # Проверяем доступность Glances API
        response = requests.get(f"{server.get_glances_url()}/api/3/all", timeout=5)
        
        if response.status_code == 200:
            server.status = 'online'
            server.last_check = datetime.datetime.utcnow()
            
            # Получаем и сохраняем метрики
            data = response.json()
            metrics = ExternalServerMetric(
                external_server_id=server.id,
                cpu_usage=data.get('cpu', {}).get('total', {}).get('user', 0) if 'cpu' in data else 0,
                memory_usage=data.get('mem', {}).get('percent', 0) if 'mem' in data else 0,
                disk_usage=data.get('fs', [{}])[0].get('percent', 0) if 'fs' in data and data.get('fs') else 0,
                load_average=str(data.get('load', {}).get('min1', 0)) if 'load' in data else '0',
                collection_method='glances_api',
                timestamp=datetime.datetime.utcnow()
            )
            
            db.session.add(metrics)
            db.session.commit()
            
            flash(f'Сервер {server.name} в сети и метрики успешно получены', 'success')
        else:
            server.status = 'offline'
            server.last_check = datetime.datetime.utcnow()
            db.session.commit()
            flash(f'Сервер {server.name} не отвечает. Код ответа: {response.status_code}', 'warning')
            
    except Exception as e:
        logger.error(f"Ошибка при проверке доступности внешнего сервера {server.name}: {str(e)}")
        server.status = 'offline'
        server.last_check = datetime.datetime.utcnow()
        db.session.commit()
        flash(f'Ошибка при проверке сервера {server.name}: {str(e)}', 'danger')
    
    return redirect(url_for('external_servers.view', server_id=server.id))