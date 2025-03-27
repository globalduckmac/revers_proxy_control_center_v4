"""
Заглушка для MQTT модуля
Этот модуль отключен и сохранен только для обратной совместимости
"""

import logging

logger = logging.getLogger(__name__)

class MQTTManager:
    """
    Заглушка для MQTTManager
    """
    
    # Топики для коммуникации (использовались в предыдущих версиях)
    TOPIC_METRICS = "servers/{server_id}/metrics"
    TOPIC_STATUS = "servers/{server_id}/status"
    TOPIC_CONTROL = "servers/{server_id}/control"
    
    def __init__(self, *args, **kwargs):
        """
        Заглушка для инициализации
        """
        logger.info("MQTT functionality is disabled")
        self.connected = False
    
    def connect(self, *args, **kwargs):
        """
        Заглушка для метода подключения
        """
        logger.info("MQTT connect() called but functionality is disabled")
        return False
    
    def disconnect(self, *args, **kwargs):
        """
        Заглушка для метода отключения
        """
        logger.info("MQTT disconnect() called but functionality is disabled")
        return
    
    def send_control_command(self, *args, **kwargs):
        """
        Заглушка для метода отправки команд
        """
        logger.info("MQTT send_control_command() called but functionality is disabled")
        return False
    
    def _subscribe_to_server_topics(self, *args, **kwargs):
        """
        Заглушка для метода подписки на топики
        """
        logger.info("MQTT _subscribe_to_server_topics() called but functionality is disabled")
        return
    
    def _on_connect(self, *args, **kwargs):
        """
        Заглушка для обработчика подключения
        """
        return
    
    def _on_message(self, *args, **kwargs):
        """
        Заглушка для обработчика сообщений
        """
        return
    
    def _on_disconnect(self, *args, **kwargs):
        """
        Заглушка для обработчика отключения
        """
        return