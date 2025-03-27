"""
Скрипт для очистки проекта от зависимостей MQTT
Удаляет или заменяет все ссылки на MQTT модули

Для запуска используйте:
python deploy_mqtt_cleanup.py
"""

import os
import sys
import re
import shutil
from pathlib import Path

def create_mqtt_manager_stub():
    """Создает заглушку для mqtt_manager.py"""
    mqtt_stub = """\"\"\"
Заглушка для отключенной MQTT функциональности
\"\"\"

import logging

logger = logging.getLogger(__name__)

class MQTTManager:
    \"\"\"Заглушка для MQTT функциональности\"\"\"

    # Топики для совместимости с существующим кодом
    TOPIC_METRICS = "servers/{server_id}/metrics"
    TOPIC_STATUS = "servers/{server_id}/status"
    TOPIC_CONTROL = "servers/{server_id}/control"

    def __init__(self):
        \"\"\"Заглушка инициализации\"\"\"
        self.connected = False

    def connect(self):
        \"\"\"Заглушка для connect()\"\"\"
        return False

    def disconnect(self):
        \"\"\"Заглушка для disconnect()\"\"\"
        pass

    def send_control_command(self, *args, **kwargs):
        \"\"\"Заглушка для send_control_command()\"\"\"
        return False

    def _subscribe_to_server_topics(self):
        \"\"\"Заглушка для _subscribe_to_server_topics()\"\"\"
        pass

    def _on_connect(self, *args, **kwargs):
        \"\"\"Заглушка для _on_connect()\"\"\"
        pass

    def _on_message(self, *args, **kwargs):
        \"\"\"Заглушка для _on_message()\"\"\"
        pass

    def _on_disconnect(self, *args, **kwargs):
        \"\"\"Заглушка для _on_disconnect()\"\"\"
        pass
"""
    
    with open('modules/mqtt_manager.py', 'w') as f:
        f.write(mqtt_stub)
    print("✅ Создана заглушка mqtt_manager.py")

def process_routes_settings_py():
    """Обрабатывает файл routes/settings.py для удаления MQTT функциональности"""
    if not os.path.exists('routes/settings.py'):
        print("❌ File routes/settings.py not found")
        return
        
    with open('routes/settings.py', 'r') as f:
        content = f.read()
    
    # Замена импорта на заглушку
    content = re.sub(r'import paho\.mqtt\.client as mqtt', '# MQTT disabled', content)
    
    # Обработка MQTT методов
    mqtt_routes = [
        r'@bp\.route\(\'/mqtt\'.*?def mqtt\(\).*?return.*?\)',
        r'@bp\.route\(\'/update_mqtt\'.*?def update_mqtt\(\).*?return.*?\)',
        r'@bp\.route\(\'/test_mqtt_connection\'.*?def test_mqtt_connection\(\).*?return.*?\)'
    ]
    
    for route_pattern in mqtt_routes:
        # Поиск паттерна с включением многострочного режима (re.DOTALL)
        match = re.search(route_pattern, content, re.DOTALL)
        if match:
            # Создание заглушки для метода
            method_name = re.search(r'def ([^(]+)\(', match.group(0))
            if method_name:
                stub = f"""
@bp.route('/{method_name.group(1)}')
@login_required
def {method_name.group(1)}():
    \"\"\"
    MQTT функциональность отключена
    \"\"\"
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам', 'danger')
        return redirect(url_for('main.index'))
    
    flash('MQTT функциональность отключена', 'warning')
    return redirect(url_for('settings.general'))
"""
                # Замена найденного блока на заглушку
                content = content.replace(match.group(0), stub)
    
    with open('routes/settings.py', 'w') as f:
        f.write(content)
    
    print("✅ Обработан routes/settings.py")

def process_tasks_py():
    """Обрабатывает файл tasks.py для удаления MQTT функциональности"""
    if not os.path.exists('tasks.py'):
        print("❌ File tasks.py not found")
        return

    with open('tasks.py', 'r') as f:
        content = f.read()
    
    # Удаляем импорт MQTTManager, если он есть
    content = re.sub(r'from modules\.mqtt_manager import MQTTManager', '# MQTT disabled', content)
    
    # Заменяем инициализацию MQTT
    mqtt_init_pattern = r'mqtt_manager = MQTTManager\(\).*?mqtt_manager\.connect\(\)'
    if re.search(mqtt_init_pattern, content, re.DOTALL):
        content = re.sub(mqtt_init_pattern, '# MQTT functionality is disabled', content, flags=re.DOTALL)
    
    with open('tasks.py', 'w') as f:
        f.write(content)
    
    print("✅ Обработан tasks.py")

def process_app_py():
    """Обрабатывает файл app.py для удаления MQTT инициализации"""
    if not os.path.exists('app.py'):
        print("❌ File app.py not found")
        return

    with open('app.py', 'r') as f:
        content = f.read()
    
    # Удаляем импорт MQTTManager, если он есть
    content = re.sub(r'from modules\.mqtt_manager import MQTTManager', '# MQTT disabled', content)
    
    # Удаляем инициализацию MQTT
    mqtt_init_pattern = r'mqtt_manager = MQTTManager\(\).*?mqtt_manager\.connect\(\)'
    if re.search(mqtt_init_pattern, content, re.DOTALL):
        content = re.sub(mqtt_init_pattern, '# MQTT functionality is disabled', content, flags=re.DOTALL)
    
    with open('app.py', 'w') as f:
        f.write(content)
    
    print("✅ Обработан app.py")

def process_pyproject_toml():
    """Обрабатывает файл pyproject.toml для удаления зависимости paho-mqtt"""
    if not os.path.exists('pyproject.toml'):
        print("❌ File pyproject.toml not found")
        return
        
    with open('pyproject.toml', 'r') as f:
        content = f.read()
    
    # Удаляем paho-mqtt из зависимостей
    content = re.sub(r'["\'](paho-mqtt)["\'].*?,?\n', '', content)
    
    with open('pyproject.toml', 'w') as f:
        f.write(content)
    
    print("✅ Обработан pyproject.toml")

def process_deploy_script():
    """Обрабатывает скрипт деплоя для удаления установки paho-mqtt"""
    for script_name in ['deploy_script.sh', 'deploy_script_v2.sh']:
        if not os.path.exists(script_name):
            print(f"❌ File {script_name} not found")
            continue
            
        with open(script_name, 'r') as f:
            content = f.read()
        
        # Удаляем установку paho-mqtt
        content = re.sub(r'pip.*?install.*?paho-mqtt', '# MQTT dependency removed', content)
        
        with open(script_name, 'w') as f:
            f.write(content)
        
        print(f"✅ Обработан {script_name}")

def process_monitoring_py():
    """Обрабатывает файл monitoring.py для удаления зависимости от MQTT"""
    if not os.path.exists('modules/monitoring.py'):
        print("❌ File modules/monitoring.py not found")
        return
        
    with open('modules/monitoring.py', 'r') as f:
        content = f.read()
    
    # Закомментируем импорт MQTT
    content = re.sub(r'from modules\.mqtt_manager import MQTTManager', '# MQTT disabled\n# from modules.mqtt_manager import MQTTManager', content)
    
    # Заменим метод collect_server_metrics_mqtt на заглушку
    mqtt_method_pattern = r'def collect_server_metrics_mqtt.*?return.*?\n'
    mqtt_stub = """    @staticmethod
    def collect_server_metrics_mqtt(server):
        \"\"\"
        Заглушка: MQTT функциональность отключена
        
        Args:
            server: объект Server для сбора метрик
            
        Returns:
            ServerMetric: всегда None
        \"\"\"
        logger.info(f"MQTT collection method is disabled for server {server.name}")
        return None
        
"""
    if re.search(mqtt_method_pattern, content, re.DOTALL):
        content = re.sub(mqtt_method_pattern, mqtt_stub, content, flags=re.DOTALL)
    
    with open('modules/monitoring.py', 'w') as f:
        f.write(content)
    
    print("✅ Обработан modules/monitoring.py")

def main():
    """Основная функция для выполнения очистки MQTT"""
    print("Starting MQTT cleanup process...")
    
    # Проверяем, что скрипт запущен из корневой директории проекта
    if not os.path.exists('modules') or not os.path.exists('routes'):
        print("❌ Error: This script must be run from the project root directory")
        print(f"Current directory: {os.getcwd()}")
        sys.exit(1)
    
    # Создаем заглушку для mqtt_manager.py
    create_mqtt_manager_stub()
    
    # Обрабатываем файлы для удаления зависимостей
    process_routes_settings_py()
    process_tasks_py()
    process_app_py()
    process_pyproject_toml()
    process_deploy_script()
    process_monitoring_py()
    
    print("\n✅ MQTT cleanup completed successfully!")
    print("You should now rebuild the project and restart the service.")

if __name__ == "__main__":
    main()