"""
Маршруты для управления Glances на серверах.
"""

import logging
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from modules.glances_manager import GlancesManager
from models import db, Server

# Настройка логирования
logger = logging.getLogger(__name__)

# Создание blueprint
bp = Blueprint('glances', __name__, url_prefix='/glances')

@bp.route('/')
@login_required
def index():
    """Отображает основную страницу Glances мониторинга."""
    servers = Server.query.all()
    return render_template('glances/index.html', servers=servers)

@bp.route('/server/<int:server_id>')
@login_required
def server_detail(server_id):
    """Отображает детальную информацию о мониторинге сервера через Glances."""
    server = Server.query.get_or_404(server_id)
    
    # Проверка статуса Glances на сервере
    status = GlancesManager.check_glances_status(server_id)
    
    # Получаем последние метрики, если Glances активен
    metrics = None
    if status.get('api_accessible', False):
        metrics = GlancesManager.get_detailed_metrics(server_id)
    
    return render_template(
        'glances/server_detail.html', 
        server=server, 
        status=status,
        metrics=metrics
    )

@bp.route('/install/<int:server_id>', methods=['POST'])
@login_required
def install(server_id):
    """Устанавливает Glances на выбранный сервер."""
    # Получаем параметры из формы
    api_port = request.form.get('api_port', 61208)
    web_port = request.form.get('web_port', 61209)
    
    try:
        api_port = int(api_port)
        web_port = int(web_port)
    except ValueError:
        flash('Порты должны быть числами', 'danger')
        return redirect(url_for('glances.index'))
    
    # Устанавливаем Glances
    result = GlancesManager.install_glances(server_id, api_port, web_port)
    
    if result.get('success', False):
        flash(f'Glances успешно установлен: {result.get("message", "")}', 'success')
    else:
        flash(f'Ошибка установки Glances: {result.get("message", "")}', 'danger')
    
    return redirect(url_for('glances.server_detail', server_id=server_id))

@bp.route('/enable/<int:server_id>', methods=['POST'])
@login_required
def enable(server_id):
    """Включает мониторинг с помощью Glances для выбранного сервера."""
    server = Server.query.get_or_404(server_id)
    
    # Включаем Glances
    server.glances_enabled = True
    db.session.commit()
    
    flash('Мониторинг с помощью Glances включен', 'success')
    return redirect(url_for('glances.server_detail', server_id=server_id))

@bp.route('/disable/<int:server_id>', methods=['POST'])
@login_required
def disable(server_id):
    """Отключает мониторинг с помощью Glances для выбранного сервера."""
    server = Server.query.get_or_404(server_id)
    
    # Отключаем Glances
    server.glances_enabled = False
    db.session.commit()
    
    flash('Мониторинг с помощью Glances отключен', 'success')
    return redirect(url_for('glances.server_detail', server_id=server_id))

@bp.route('/restart/<int:server_id>', methods=['POST'])
@login_required
def restart(server_id):
    """Перезапускает сервис Glances на выбранном сервере."""
    result = GlancesManager.restart_glances_service(server_id)
    
    if result.get('success', False):
        flash(f'Сервис Glances успешно перезапущен: {result.get("message", "")}', 'success')
    else:
        flash(f'Ошибка перезапуска Glances: {result.get("message", "")}', 'danger')
    
    return redirect(url_for('glances.server_detail', server_id=server_id))

@bp.route('/collect/<int:server_id>', methods=['POST'])
@login_required
def collect_metrics(server_id):
    """Вручную запускает сбор метрик с сервера."""
    result = GlancesManager.collect_server_metrics(server_id)
    
    if result.get('success', False):
        flash(f'Метрики успешно собраны: CPU={result.get("cpu_usage")}%, MEM={result.get("memory_usage")}%, DISK={result.get("disk_usage")}%', 'success')
    else:
        flash(f'Ошибка сбора метрик: {result.get("message", "")}', 'danger')
    
    return redirect(url_for('glances.server_detail', server_id=server_id))

@bp.route('/check/<int:server_id>', methods=['POST'])
@login_required
def check_status(server_id):
    """Проверяет статус Glances на выбранном сервере."""
    result = GlancesManager.check_glances_status(server_id)
    
    if result.get('success', False):
        status_message = f'Статус Glances: Сервис {"запущен" if result.get("running") else "остановлен"}, API {"доступен" if result.get("api_accessible") else "недоступен"}'
        flash(status_message, 'info')
    else:
        flash(f'Ошибка проверки статуса Glances: {result.get("message", "")}', 'danger')
    
    return redirect(url_for('glances.server_detail', server_id=server_id))

@bp.route('/api/metrics/<int:server_id>')
@login_required
def api_get_metrics(server_id):
    """API-эндпоинт для получения текущих метрик сервера."""
    result = GlancesManager.collect_server_metrics(server_id)
    return jsonify(result)

@bp.route('/api/detailed/<int:server_id>')
@login_required
def api_get_detailed(server_id):
    """API-эндпоинт для получения детальных метрик сервера."""
    result = GlancesManager.get_detailed_metrics(server_id)
    return jsonify(result)

@bp.route('/api/status/<int:server_id>')
@login_required
def api_get_status(server_id):
    """API-эндпоинт для получения статуса Glances на сервере."""
    result = GlancesManager.check_glances_status(server_id)
    return jsonify(result)