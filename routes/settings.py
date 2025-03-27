"""
Маршруты для настроек системы
"""

import logging
from datetime import datetime, timedelta
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app as app
from flask_login import login_required, current_user

# Заглушка для MQTT
from modules.mqtt_manager import MQTTManager
from modules.nginx_manager import NginxManager
from modules.server_manager import ServerManager
from modules.telegram_manager import TelegramManager
from models import SystemSetting, Server, ServerGroup
from app import db

bp = Blueprint('settings', __name__)
logger = logging.getLogger(__name__)

# Список настроек системы и их описаний
SYSTEM_SETTINGS = {
    # Основные настройки
    'system_name': ('Название системы', False),
    'company_name': ('Название компании', False),
    'admin_email': ('Email администратора', False),
    'maintenance_mode': ('Режим обслуживания', False),
    'default_ssh_port': ('SSH порт по умолчанию', False),
    'ssh_timeout': ('Таймаут SSH подключения (сек)', False),
    'ssh_command_timeout': ('Таймаут SSH команд (сек)', False),
    'template_update_interval': ('Интервал обновления конфигурации (часы)', False),
    'logs_retention_days': ('Хранение логов (дни)', False),
    'metrics_retention_days': ('Хранение метрик (дни)', False),
    'ssl_certificates_path': ('Путь к SSL сертификатам', False),
    
    # Настройки уведомлений
    'notifications_enabled': ('Уведомления включены', False),
    'notify_on_server_down': ('Уведомлять о недоступности серверов', False),
    'notify_on_ssl_expiration': ('Уведомлять об истечении SSL', False),
    'ssl_expiration_warning_days': ('Дней до истечения SSL для уведомления', False),
    'notify_on_disk_usage': ('Уведомлять о заполнении диска', False),
    'disk_usage_warning_percent': ('Процент заполнения диска для уведомления', False),
    
    # Настройки Telegram
    'telegram_enabled': ('Telegram уведомления включены', False),
    'telegram_bot_token': ('Токен Telegram бота', True),
    'telegram_chat_id': ('ID чата Telegram', False),
    
    # Настройки SSL
    'ssl_auto_renewal': ('Автоматическое обновление SSL', False),
    'ssl_renewal_command': ('Команда обновления SSL', False),
    'ssl_check_interval': ('Интервал проверки SSL (часы)', False),
    
    # Настройки проверки доменов
    'domain_check_enabled': ('Проверка доменов включена', False),
    'domain_check_interval': ('Интервал проверки доменов (часы)', False),
    'domain_check_timeout': ('Таймаут проверки доменов (сек)', False),
    'domain_check_retries': ('Количество повторных попыток проверки', False),
    
    # Интеграция с GitHub
    'github_enabled': ('Интеграция с GitHub включена', False),
    'github_token': ('GitHub токен', True),
    'github_username': ('GitHub пользователь', False),
    'github_repo': ('GitHub репозиторий', False),
    'github_branch': ('GitHub ветка', False),
    
    # Интеграция с FFPanel
    'ffpanel_enabled': ('Интеграция с FFPanel включена', False),
    'ffpanel_token': ('FFPanel токен', True),
    'ffpanel_api_url': ('FFPanel API URL', False),
    'ffpanel_sync_interval': ('Интервал синхронизации с FFPanel (часы)', False),
    
    # Настройки мониторинга
    'monitoring_enabled': ('Мониторинг включен', False),
    'monitoring_interval': ('Интервал мониторинга (минуты)', False),
    'monitoring_retry_interval': ('Интервал повторных попыток (минуты)', False),
    'status_check_interval': ('Интервал проверки статуса (минуты)', False),
    
    # Настройки для интеграции с Netdata
    'netdata_enabled': ('Интеграция с Netdata включена', False),
    'netdata_default_port': ('Порт Netdata по умолчанию', False),
    
    # Настройки для интеграции с Glances
    'glances_enabled': ('Интеграция с Glances включена', False),
    'glances_default_port': ('Порт Glances по умолчанию', False),
    'glances_auto_install': ('Автоматическая установка Glances', False),
    
    # Настройки MQTT (отключены)
    'mqtt_broker_host': ('Адрес MQTT брокера', False),
    'mqtt_broker_port': ('Порт MQTT брокера', False),
    'mqtt_username': ('Имя пользователя MQTT', False),
    'mqtt_password': ('Пароль MQTT', True),
    'mqtt_enabled': ('MQTT мониторинг включен', False)
}

@bp.route('/')
@login_required
def index():
    """
    Главная страница настроек
    """
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам', 'danger')
        return redirect(url_for('main.index'))
        
    # Проверяем, включен ли режим обслуживания
    maintenance_mode = SystemSetting.get_value('maintenance_mode', 'false') == 'true'
    
    # Получаем настройки для отображения
    system_name = SystemSetting.get_value('system_name', 'Reverse Proxy Control Center')
    admin_email = SystemSetting.get_value('admin_email', '')
    logs_retention_days = SystemSetting.get_value('logs_retention_days', '30')
    metrics_retention_days = SystemSetting.get_value('metrics_retention_days', '90')
    
    # Статистика серверов и доменов
    server_count = Server.query.count()
    server_groups = ServerGroup.query.all()
    
    return render_template('settings/index.html', 
                          maintenance_mode=maintenance_mode,
                          system_name=system_name,
                          admin_email=admin_email,
                          logs_retention_days=logs_retention_days,
                          metrics_retention_days=metrics_retention_days,
                          server_count=server_count,
                          server_groups=server_groups)
                          
@bp.route('/general', methods=['GET', 'POST'])
@login_required
def general():
    """
    Управление общими настройками системы
    """
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам', 'danger')
        return redirect(url_for('main.index'))
    
    # Обработка POST запроса для сохранения настроек    
    if request.method == 'POST':
        # Сохраняем все настройки из формы
        for key in request.form:
            if key in SYSTEM_SETTINGS:
                is_protected = SYSTEM_SETTINGS[key][1]
                description = SYSTEM_SETTINGS[key][0]
                
                # Для чекбоксов преобразуем в строковый формат
                if key in request.form:
                    if request.form[key] == 'on':
                        value = 'true'
                    else:
                        value = request.form[key]
                else:
                    value = 'false'
                    
                # Сохраняем настройку
                SystemSetting.set_value(key, value, description, is_protected)
        
        flash('Настройки успешно сохранены', 'success')
        return redirect(url_for('settings.general'))
    
    # Получаем все системные настройки
    settings = {}
    for key, (description, is_protected) in SYSTEM_SETTINGS.items():
        # Получаем текущее значение или значение по умолчанию
        if key.endswith('_enabled'):
            settings[key] = SystemSetting.get_value(key, 'false') == 'true'
        else:
            settings[key] = SystemSetting.get_value(key, '')
    
    return render_template('settings/general.html', 
                          settings=settings,
                          setting_descriptions=SYSTEM_SETTINGS)

@bp.route('/mqtt')
@login_required
def mqtt():
    """
    Страница управления настройками MQTT (отключено)
    """
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам', 'danger')
        return redirect(url_for('main.index'))
    
    # Получаем настройки MQTT
    mqtt_broker_host = SystemSetting.get_value('mqtt_broker_host', 'localhost')
    mqtt_broker_port = SystemSetting.get_value('mqtt_broker_port', '1883')
    mqtt_username = SystemSetting.get_value('mqtt_username', '')
    mqtt_password = SystemSetting.get_value('mqtt_password', '')
    mqtt_enabled = SystemSetting.get_value('mqtt_enabled', 'false') == 'true'
    
    # Получаем список серверов
    servers = Server.query.all()
    
    # Проверяем подключение к MQTT (всегда будет False, т.к. MQTT отключен)
    mqtt_connected = False
    
    # Статус MQTT брокера
    mqtt_status = {}
    
    # Функционал отключен - отображаем сообщение об этом
    flash('MQTT функциональность отключена в этой версии', 'warning')
        
    return render_template('settings/mqtt.html', 
                          mqtt_broker_host=mqtt_broker_host,
                          mqtt_broker_port=mqtt_broker_port,
                          mqtt_username=mqtt_username,
                          mqtt_password=mqtt_password,
                          mqtt_enabled=mqtt_enabled,
                          mqtt_connected=mqtt_connected,
                          servers=servers,
                          mqtt_status=mqtt_status,
                          feature_disabled=True)

@bp.route('/update_mqtt', methods=['POST'])
@login_required
def update_mqtt():
    """
    Обработчик формы настроек MQTT (отключено)
    """
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам', 'danger')
        return redirect(url_for('main.index'))
    
    # Функционал отключен - выводим сообщение
    flash('MQTT функциональность отключена в этой версии', 'warning')
    
    # Для обратной совместимости сохраняем настройки
    mqtt_broker_host = request.form.get('mqtt_broker_host', 'localhost').strip()
    mqtt_broker_port = request.form.get('mqtt_broker_port', '1883').strip()
    mqtt_username = request.form.get('mqtt_username', '').strip()
    mqtt_password = request.form.get('mqtt_password', '').strip()
    mqtt_enabled = 'mqtt_enabled' in request.form
    
    # Сохраняем настройки в базе данных
    SystemSetting.set_value('mqtt_broker_host', mqtt_broker_host, 'Адрес MQTT брокера', False)
    SystemSetting.set_value('mqtt_broker_port', mqtt_broker_port, 'Порт MQTT брокера', False)
    SystemSetting.set_value('mqtt_username', mqtt_username, 'Имя пользователя MQTT', False)
    SystemSetting.set_value('mqtt_enabled', 'true' if mqtt_enabled else 'false', 'MQTT мониторинг включен', False)
    
    # Сохраняем пароль только если он был указан
    if mqtt_password:
        SystemSetting.set_value('mqtt_password', mqtt_password, 'Пароль MQTT', True)
    
    # Проверка подключения (всегда будет ложной)
    if mqtt_enabled:
        flash('MQTT интеграция отключена в данной версии. Настройки сохранены, но функция не работает.', 'warning')
    
    return redirect(url_for('settings.mqtt'))

@bp.route('/test_mqtt_connection')
@login_required
def test_mqtt_connection():
    """
    Проверка подключения к MQTT брокеру (отключено)
    """
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам', 'danger')
        return redirect(url_for('main.index'))
    
    # Получаем настройки MQTT
    mqtt_broker_host = SystemSetting.get_value('mqtt_broker_host', 'localhost')
    mqtt_broker_port = int(SystemSetting.get_value('mqtt_broker_port', '1883'))
    mqtt_username = SystemSetting.get_value('mqtt_username', '')
    mqtt_password = SystemSetting.get_value('mqtt_password', '')
    mqtt_enabled = SystemSetting.get_value('mqtt_enabled', 'false') == 'true'
    
    # Проверка всегда отрицательная
    flash('MQTT функциональность отключена в этой версии', 'warning')
    
    return redirect(url_for('settings.mqtt'))