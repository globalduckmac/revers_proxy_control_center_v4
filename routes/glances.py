"""
Маршруты для работы с мониторингом серверов через Glances
"""

import logging
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required

from app import db
from models import Server
from modules.glances_manager import get_server_metrics, get_server_health

# Создаем блюпринт для маршрутов Glances
bp = Blueprint('glances', __name__, url_prefix='/glances')

logger = logging.getLogger(__name__)


@bp.route('/')
@login_required
def index():
    """
    Отображает страницу со всеми серверами и их статусом мониторинга Glances
    """
    servers = Server.query.all()
    return render_template('glances/index.html', servers=servers)


@bp.route('/server/<int:server_id>')
@login_required
def server_detail(server_id):
    """
    Отображает детальную информацию о сервере, полученную через Glances API
    """
    server = Server.query.get_or_404(server_id)
    
    # Получаем текущие метрики сервера
    metrics = get_server_metrics(server.ip_address, server.glances_port or 61208)
    health = get_server_health(server.ip_address, server.glances_port or 61208)
    
    return render_template(
        'glances/server_detail.html',
        server=server,
        metrics=metrics,
        health=health
    )


@bp.route('/api/server/<int:server_id>/metrics')
@login_required
def get_server_metrics_api(server_id):
    """
    API-эндпоинт для получения текущих метрик сервера
    """
    server = Server.query.get_or_404(server_id)
    
    metrics = get_server_metrics(server.ip_address, server.glances_port or 61208)
    if not metrics:
        return jsonify({'error': 'Не удалось получить метрики. Сервер недоступен или Glances не настроен.'}), 404
    
    return jsonify(metrics)


@bp.route('/api/server/<int:server_id>/health')
@login_required
def get_server_health_api(server_id):
    """
    API-эндпоинт для получения текущего состояния здоровья сервера
    """
    server = Server.query.get_or_404(server_id)
    
    health = get_server_health(server.ip_address, server.glances_port or 61208)
    if not health:
        return jsonify({'error': 'Не удалось получить состояние. Сервер недоступен или Glances не настроен.'}), 404
    
    return jsonify(health)


@bp.route('/diagnose/<int:server_id>', methods=['GET', 'POST'])
@login_required
def diagnose(server_id):
    """
    Страница диагностики и исправления проблем с Glances
    """
    server = Server.query.get_or_404(server_id)
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'enable_glances':
            server.glances_enabled = True
            server.glances_error = False
            db.session.commit()
            flash('Мониторинг Glances активирован для сервера', 'success')
        
        elif action == 'disable_glances':
            server.glances_enabled = False
            db.session.commit()
            flash('Мониторинг Glances деактивирован для сервера', 'success')
        
        elif action == 'reset_error':
            server.glances_error = False
            db.session.commit()
            flash('Статус ошибки Glances сброшен', 'success')
        
        elif action == 'update_port':
            try:
                new_port = int(request.form.get('glances_port', 61208))
                if 1 <= new_port <= 65535:
                    server.glances_port = new_port
                    db.session.commit()
                    flash(f'Порт Glances обновлен на {new_port}', 'success')
                else:
                    flash('Некорректный порт. Должен быть в диапазоне 1-65535', 'danger')
            except ValueError:
                flash('Некорректный формат порта', 'danger')
        
        return redirect(url_for('glances.diagnose', server_id=server.id))
    
    # Проверяем текущий статус Glances
    glances_available = False
    try:
        metrics = get_server_metrics(server.ip_address, server.glances_port or 61208)
        glances_available = metrics is not None
    except Exception as e:
        logger.error(f"Ошибка при проверке доступности Glances на сервере {server.name}: {str(e)}")
    
    return render_template(
        'glances/diagnose.html',
        server=server,
        glances_available=glances_available
    )