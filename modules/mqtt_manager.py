"""
Заглушка для модуля MQTT, который полностью удален из системы.
Этот файл существует только для обратной совместимости с существующим кодом.
"""

class MQTTManager:
    """Пустой класс для обратной совместимости"""
    
    # Константы для совместимости
    TOPIC_METRICS = ""
    TOPIC_STATUS = ""
    TOPIC_CONTROL = ""
    
    def __init__(self):
        pass
        
    def connect(self):
        return False
        
    def disconnect(self):
        pass
        
    def send_control_command(self, *args, **kwargs):
        return False