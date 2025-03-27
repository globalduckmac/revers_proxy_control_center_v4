#!/bin/bash

# Скрипт для полного удаления зависимостей от MQTT

# Проверяем, что скрипт запущен от имени root
if [ "$EUID" -ne 0 ]; then
  echo "Пожалуйста, запустите скрипт с правами root (sudo)"
  exit 1
fi

# Определяем директорию установки
APP_DIR="/opt/reverse-proxy-control-center"
cd "$APP_DIR" || { echo "Директория $APP_DIR не найдена"; exit 1; }

# Создаем пустую заглушку для mqtt_manager.py, чтобы удалить все MQTT зависимости
cat > "$APP_DIR/modules/mqtt_manager.py" <<EOF
"""
Заглушка для отключенной MQTT функциональности
"""

import logging

logger = logging.getLogger(__name__)

class MQTTManager:
    """Заглушка для MQTT функциональности"""

    # Топики для совместимости с существующим кодом
    TOPIC_METRICS = "servers/{server_id}/metrics"
    TOPIC_STATUS = "servers/{server_id}/status"
    TOPIC_CONTROL = "servers/{server_id}/control"

    def __init__(self):
        """Заглушка инициализации"""
        self.connected = False

    def connect(self):
        """Заглушка для connect()"""
        return False

    def disconnect(self):
        """Заглушка для disconnect()"""
        pass

    def send_control_command(self, *args, **kwargs):
        """Заглушка для send_control_command()"""
        return False

    def _subscribe_to_server_topics(self):
        """Заглушка для _subscribe_to_server_topics()"""
        pass

    def _on_connect(self, *args, **kwargs):
        """Заглушка для _on_connect()"""
        pass

    def _on_message(self, *args, **kwargs):
        """Заглушка для _on_message()"""
        pass

    def _on_disconnect(self, *args, **kwargs):
        """Заглушка для _on_disconnect()"""
        pass
EOF

# Обновляем routes/settings.py, чтобы убрать MQTT функциональность
if [ -f "$APP_DIR/routes/settings.py" ]; then
    echo "Обновляем routes/settings.py: отключаем MQTT функциональность..."
    # Создаем временный файл
    cat > "$APP_DIR/routes/settings.py.new" <<EOF
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
    
    flash('MQTT функциональность отключена', 'warning')
    return redirect(url_for('settings.general'))

@bp.route('/update_mqtt', methods=['POST'])
@login_required
def update_mqtt():
    """
    Обработчик формы настроек MQTT (отключено)
    """
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам', 'danger')
        return redirect(url_for('main.index'))
    
    flash('MQTT функциональность отключена', 'warning')
    return redirect(url_for('settings.general'))

@bp.route('/test_mqtt_connection')
@login_required
def test_mqtt_connection():
    """
    Проверка подключения к MQTT брокеру (отключено)
    """
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам', 'danger')
        return redirect(url_for('main.index'))
    
    flash('MQTT функциональность отключена', 'warning')
    return redirect(url_for('settings.general'))
EOF
    # Заменяем оригинальный файл
    mv "$APP_DIR/routes/settings.py.new" "$APP_DIR/routes/settings.py"
    echo "routes/settings.py обновлен"
fi

# Обновляем modules/monitoring.py для удаления зависимости от MQTT
if [ -f "$APP_DIR/modules/monitoring.py" ]; then
    echo "Обновляем modules/monitoring.py: отключаем MQTT функциональность..."
    # Создаем временный файл
    cat > "$APP_DIR/modules/monitoring.py.new" <<EOF
"""
Модуль для мониторинга серверов
Включает сбор метрик (CPU, RAM, диск) и проверку доступности
"""

import logging
from datetime import datetime

# MQTT отключен
# from modules.mqtt_manager import MQTTManager
from modules.server_manager import ServerManager
from modules.glances_manager import GlancesManager
from app import db
from models import Server, ServerMetric, SystemSetting

# Настройка логирования
logger = logging.getLogger(__name__)

class MonitoringManager:
    """
    Менеджер для мониторинга серверов и сбора метрик
    """
    
    @staticmethod
    def check_server_status(server):
        """
        Проверяет статус сервера через Glances API
        
        Args:
            server: объект Server для проверки
            
        Returns:
            bool: True если сервер доступен, False иначе
        """
        try:
            # Сначала пробуем через Glances API как приоритетный метод
            if GlancesManager.check_glances_availability(server):
                return True
            
            # Если Glances недоступен, пробуем SSH как запасной вариант
            if ServerManager.check_connectivity(server):
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error in server status check: {str(e)}")
            return False
            
    @staticmethod
    def collect_server_metrics(server):
        """
        Собирает метрики сервера (CPU, RAM, Disk) через Glances API или SSH
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            dict: Словарь с метриками или None в случае ошибки
        """
        try:
            # MQTT отключен - не используем его для сбора метрик
            
            # Пробуем через Glances API как первый приоритет
            if server.glances_enabled:
                logger.info(f"Attempting to collect metrics via Glances API for server {server.name}")
                metric = MonitoringManager.collect_server_metrics_glances(server)
                if metric:
                    return metric
                else:
                    # Если Glances API не сработал, помечаем сервер как имеющий проблемы с Glances
                    server.glances_error = True
                    db.session.commit()
            
            # Пробуем через SSH как резервный вариант
            logger.info(f"Falling back to SSH method for server {server.name}")
            return MonitoringManager.collect_server_metrics_ssh(server)
        except Exception as e:
            logger.error(f"Error in server metrics collection: {str(e)}")
            return None
    
    @staticmethod
    def collect_server_metrics_mqtt(server):
        """
        Заглушка: MQTT функциональность отключена
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            ServerMetric: всегда None
        """
        logger.info(f"MQTT collection method is disabled for server {server.name}")
        return None
    
    @staticmethod
    def collect_server_metrics_glances(server):
        """
        Собирает метрики сервера через Glances API
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            ServerMetric: объект с метриками или None в случае ошибки
        """
        try:
            # Получаем метрики через Glances API
            metrics = GlancesManager.get_server_metrics(server)
            
            if not metrics:
                logger.warning(f"Failed to collect metrics via Glances API for {server.name}, marking Glances as error")
                server.glances_error = True
                db.session.commit()
                return None
                
            # Если метрики получены успешно, создаем объект ServerMetric
            metric = ServerMetric(
                server_id=server.id,
                cpu_usage=metrics['cpu'],
                memory_usage=metrics['memory'],
                disk_usage=metrics['disk'],
                load_average=metrics['load'],
                timestamp=datetime.now(),
                collection_method='glances'  # Помечаем, что метрики собраны через Glances
            )
            
            # Сохраняем метрики в базе данных
            db.session.add(metric)
            db.session.commit()
            
            # Сбрасываем флаг ошибки Glances, если он был установлен
            if server.glances_error:
                server.glances_error = False
                db.session.commit()
                
            logger.info(f"Collected server metrics via Glances API for {server.name}: CPU {metrics['cpu']}%, Memory {metrics['memory']}%, Disk {metrics['disk']}%")
            
            return metric
        except Exception as e:
            logger.error(f"Error collecting metrics via Glances for {server.name}: {str(e)}")
            server.glances_error = True
            db.session.commit()
            return None
    
    @staticmethod
    def collect_server_metrics_ssh(server):
        """
        Собирает метрики сервера через SSH
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            ServerMetric: объект с метриками или None в случае ошибки
        """
        try:
            # Проверяем соединение с сервером
            if not ServerManager.check_connectivity(server):
                logger.warning(f"Server {server.name} is not reachable via SSH, skipping metrics collection")
                return None
            
            # Получаем метрики через SSH
            cpu_usage = ServerManager.get_cpu_usage(server)
            memory_usage = ServerManager.get_memory_usage(server)
            disk_usage = ServerManager.get_disk_usage(server)
            load_average = ServerManager.get_load_average(server)
            
            # Создаем объект ServerMetric
            metric = ServerMetric(
                server_id=server.id,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                disk_usage=disk_usage,
                load_average=load_average,
                timestamp=datetime.now(),
                collection_method='ssh'  # Помечаем, что метрики собраны через SSH
            )
            
            # Сохраняем метрики в базе данных
            db.session.add(metric)
            db.session.commit()
            
            logger.info(f"Collected server metrics via SSH for {server.name}: CPU {cpu_usage}%, Memory {memory_usage}%, Disk {disk_usage}%")
            
            return metric
        except Exception as e:
            logger.error(f"Error collecting metrics via SSH for {server.name}: {str(e)}")
            return None
EOF
    # Заменяем оригинальный файл
    mv "$APP_DIR/modules/monitoring.py.new" "$APP_DIR/modules/monitoring.py"
    echo "modules/monitoring.py обновлен"
fi

# Обновляем deploy_script_v2.sh для удаления установки paho-mqtt
echo "Обновляем deploy_script_v2.sh для удаления зависимости paho-mqtt..."
wget -q https://raw.githubusercontent.com/globalduckmac/revers_proxy_control_center_v2/main/deploy_script_v2.sh -O "$APP_DIR/deploy_script_v2.sh"
chmod +x "$APP_DIR/deploy_script_v2.sh"
echo "deploy_script_v2.sh обновлен"

# Проверяем, установлен ли venv
if [ -d "$APP_DIR/venv" ]; then
    echo "Активируем виртуальное окружение..."
    source "$APP_DIR/venv/bin/activate"
    
    echo "Убеждаемся, что paho-mqtt не установлен..."
    pip uninstall -y paho-mqtt || true
    
    echo "Пересоздаем базу данных..."
    cd "$APP_DIR"
    source venv/bin/activate
    python -c "from app import app, db; from models import User; with app.app_context(): db.create_all(); print('База данных инициализирована')"
    
    # Пересоздаем админа если его нет
    python -c "from app import app, db; from models import User; from werkzeug.security import generate_password_hash; with app.app_context(): admin = User.query.filter_by(username='admin').first(); exists = admin is not None; if not exists: admin = User(username='admin', email='admin@example.com', password_hash=generate_password_hash('admin123'), is_admin=True); db.session.add(admin); db.session.commit(); print('Админ создан' if not exists else 'Админ уже существует')"
    
    # Перезапускаем сервисы
    echo "Перезапускаем сервисы..."
    systemctl daemon-reload
    systemctl restart reverse-proxy-control-center
    
    echo "Проверяем статус сервиса..."
    systemctl status reverse-proxy-control-center --no-pager
fi

echo "Очистка MQTT зависимостей завершена успешно."