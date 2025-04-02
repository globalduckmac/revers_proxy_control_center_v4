# -*- coding: utf-8 -*-

import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import desc
import time
from datetime import datetime

from app import db
from models import ExternalServer, ExternalServerMetric, ServerLog
from forms.external_server_forms import ExternalServerForm, ExternalServerTestForm
from modules.glances_manager import GlancesManager

# Создаем блюпринт
external_servers_blueprint = Blueprint('external_servers', __name__)

# Middleware для проверки прав администратора
@external_servers_blueprint.before_request
@login_required
def check_admin():
    """
    Проверяет, является ли текущий пользователь администратором.
    Должен быть вызван перед всеми защищенными маршрутами.
    """
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к этой странице', 'danger')
        return redirect(url_for('auth.login'))

@external_servers_blueprint.route('/')
def list_external_servers():
    """
    Отображает список всех внешних серверов
    """
    servers = ExternalServer.query.all()
    return render_template(
        'external_servers/list.html',
        servers=servers,
        title='Внешние серверы'
    )

@external_servers_blueprint.route('/add', methods=['GET', 'POST'])
def add_external_server():
    """
    Добавляет новый внешний сервер
    """
    form = ExternalServerForm()
    
    if form.validate_on_submit():
        # Создаем новый сервер
        server = ExternalServer()
        form.populate_obj(server)
        
        # Проверяем соединение с сервером перед сохранением
        try:
            status = GlancesManager.check_external_server_glances(
                server.ip_address,
                server.glances_port
            )
            
            if status:
                server.last_status = 'online'
                server.last_check = datetime.utcnow()
                flash('Соединение с сервером успешно установлено', 'success')
            else:
                server.last_status = 'offline'
                server.last_check = datetime.utcnow()
                flash('Сервер добавлен, но соединение с Glances API не установлено', 'warning')
        except Exception as e:
            server.last_status = 'error'
            server.last_check = datetime.utcnow()
            flash(f'Ошибка при проверке соединения: {str(e)}', 'danger')
        
        # Сохраняем сервер
        db.session.add(server)
        db.session.commit()
        
        # Создаем запись в журнале
        log = ServerLog(
            server_id=None,
            action='add_external_server',
            status='success',
            message=f'Добавлен новый внешний сервер: {server.name} ({server.ip_address})'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Внешний сервер {server.name} успешно добавлен', 'success')
        return redirect(url_for('external_servers.list_external_servers'))
    
    return render_template(
        'external_servers/add.html',
        form=form,
        title='Добавление внешнего сервера'
    )

@external_servers_blueprint.route('/edit/<int:server_id>', methods=['GET', 'POST'])
def edit_external_server(server_id):
    """
    Редактирует существующий внешний сервер
    """
    server = ExternalServer.query.get_or_404(server_id)
    form = ExternalServerForm(obj=server)
    
    if form.validate_on_submit():
        # Обновляем сервер
        form.populate_obj(server)
        
        # Сохраняем сервер
        db.session.commit()
        
        # Создаем запись в журнале
        log = ServerLog(
            server_id=None,
            action='edit_external_server',
            status='success',
            message=f'Внешний сервер {server.name} ({server.ip_address}) обновлен'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Внешний сервер {server.name} успешно обновлен', 'success')
        return redirect(url_for('external_servers.list_external_servers'))
    
    return render_template(
        'external_servers/edit.html',
        form=form,
        server=server,
        title=f'Редактирование сервера: {server.name}'
    )

@external_servers_blueprint.route('/delete/<int:server_id>', methods=['POST'])
def delete_external_server(server_id):
    """
    Удаляет внешний сервер
    """
    server = ExternalServer.query.get_or_404(server_id)
    
    # Создаем запись в журнале перед удалением
    log = ServerLog(
        server_id=None,
        action='delete_external_server',
        status='success',
        message=f'Удален внешний сервер: {server.name} ({server.ip_address})'
    )
    db.session.add(log)
    
    # Удаляем сервер
    db.session.delete(server)
    db.session.commit()
    
    flash(f'Внешний сервер {server.name} успешно удален', 'success')
    return redirect(url_for('external_servers.list_external_servers'))

@external_servers_blueprint.route('/test/<int:server_id>', methods=['POST'])
def test_external_server(server_id):
    """
    Проверяет соединение с внешним сервером
    """
    server = ExternalServer.query.get_or_404(server_id)
    
    try:
        # Проверяем соединение
        status = GlancesManager.check_external_server_glances(
            server.ip_address,
            server.glances_port
        )
        
        if status:
            server.last_status = 'online'
            server.last_check = datetime.utcnow()
            flash('Соединение с сервером успешно установлено', 'success')
        else:
            server.last_status = 'offline'
            server.last_check = datetime.utcnow()
            flash('Не удалось установить соединение с Glances API', 'warning')
    except Exception as e:
        server.last_status = 'error'
        server.last_check = datetime.utcnow()
        flash(f'Ошибка при проверке соединения: {str(e)}', 'danger')
    
    # Сохраняем статус
    db.session.commit()
    
    # Если запрос через AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': server.last_status,
            'message': f'Статус сервера: {server.last_status}',
            'last_check': server.last_check.strftime('%Y-%m-%d %H:%M:%S') if server.last_check else None
        })
    
    # Иначе редирект
    return redirect(url_for('external_servers.list_external_servers'))

@external_servers_blueprint.route('/check/<int:server_id>', methods=['POST'])
def check_external_server(server_id):
    """
    Проверяет соединение с внешним сервером и собирает метрики
    """
    server = ExternalServer.query.get_or_404(server_id)
    
    try:
        # Проверяем соединение
        status = GlancesManager.check_external_server_glances(
            server.ip_address,
            server.glances_port
        )
        
        if status:
            server.last_status = 'online'
            server.last_check = datetime.utcnow()
            
            # Собираем метрики
            GlancesManager.update_external_server_metrics(server)
            
            flash('Соединение установлено, метрики обновлены', 'success')
        else:
            server.last_status = 'offline'
            server.last_check = datetime.utcnow()
            flash('Не удалось установить соединение с Glances API', 'warning')
    except Exception as e:
        server.last_status = 'error'
        server.last_check = datetime.utcnow()
        flash(f'Ошибка при проверке соединения: {str(e)}', 'danger')
    
    # Сохраняем статус
    db.session.commit()
    
    # Перенаправляем на страницу мониторинга
    return redirect(url_for('external_servers.monitor_external_server', server_id=server.id))

@external_servers_blueprint.route('/monitoring/<int:server_id>')
def monitor_external_server(server_id):
    """
    Отображает страницу мониторинга внешнего сервера
    """
    server = ExternalServer.query.get_or_404(server_id)
    
    # Получаем последние метрики
    cpu_metrics = server.get_latest_metric('cpu', 'total')
    memory_metrics = server.get_latest_metric('memory', 'percent')
    disk_metrics = server.get_latest_metric('disk', 'detail')
    network_metrics = server.get_latest_metric('network', 'detail')
    
    # Получаем историю метрик для графиков
    cpu_history = server.get_metric_history('cpu', 'total', 48)  # За 48 точек (4 часа при сборе каждые 5 минут)
    memory_history = server.get_metric_history('memory', 'percent', 48)
    
    return render_template(
        'external_servers/monitoring.html',
        server=server,
        cpu_metrics=cpu_metrics,
        memory_metrics=memory_metrics,
        disk_metrics=disk_metrics,
        network_metrics=network_metrics,
        cpu_history=cpu_history,
        memory_history=memory_history,
        title=f'Мониторинг сервера: {server.name}'
    )

@external_servers_blueprint.route('/api/metrics/<int:server_id>')
def get_server_metrics_api(server_id):
    """
    API эндпоинт для получения метрик сервера в формате JSON
    """
    server = ExternalServer.query.get_or_404(server_id)
    
    # Получаем последние метрики
    cpu_metrics = server.get_latest_metric('cpu', 'total')
    memory_metrics = server.get_latest_metric('memory', 'percent')
    
    return jsonify({
        'server': {
            'id': server.id,
            'name': server.name,
            'ip_address': server.ip_address,
            'status': server.last_status,
            'last_check': server.last_check.strftime('%Y-%m-%d %H:%M:%S') if server.last_check else None
        },
        'metrics': {
            'cpu': float(cpu_metrics.metric_value) if cpu_metrics else None,
            'memory': float(memory_metrics.metric_value) if memory_metrics else None,
            'updated_at': cpu_metrics.created_at.strftime('%Y-%m-%d %H:%M:%S') if cpu_metrics else None
        }
    })