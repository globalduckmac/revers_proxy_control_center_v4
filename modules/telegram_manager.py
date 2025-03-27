"""
Модуль для работы с Telegram API
"""

import logging
import os
from datetime import datetime

import telegram
from flask import current_app

logger = logging.getLogger(__name__)

class TelegramManager:
    """
    Менеджер для работы с Telegram API
    """
    
    @staticmethod
    def send_message(message, disable_notification=False):
        """
        Отправляет сообщение в Telegram чат
        
        Args:
            message: Текст сообщения
            disable_notification: Отключить звук уведомления
            
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        try:
            # Получаем токен и chat_id из переменных окружения или настроек
            token = os.environ.get('TELEGRAM_BOT_TOKEN')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID')
            
            # Проверяем наличие необходимых данных
            if not token or not chat_id:
                logger.warning("Telegram notification not sent: missing token or chat_id in environment")
                return False
            
            # Создаем бота и отправляем сообщение
            bot = telegram.Bot(token)
            bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=telegram.ParseMode.HTML,
                disable_notification=disable_notification
            )
            
            logger.info(f"Telegram message sent successfully: {message[:100]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error sending Telegram message: {str(e)}")
            return False
    
    @staticmethod
    def send_server_status_notification(server, is_online):
        """
        Отправляет уведомление о статусе сервера
        
        Args:
            server: объект Server
            is_online: флаг статуса (True/False)
            
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        status = "🟢 доступен" if is_online else "🔴 недоступен"
        status_changed = "изменился" if server.status == is_online else "не изменился"
        
        message = f"""
<b>Статус сервера {server.name}</b>
Сервер <b>{status}</b>
IP: {server.ip_address}
Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return TelegramManager.send_message(message)
    
    @staticmethod
    def send_disk_usage_warning(server, usage_percent):
        """
        Отправляет предупреждение о заполнении диска
        
        Args:
            server: объект Server
            usage_percent: Процент заполнения диска
            
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        message = f"""
<b>⚠️ Предупреждение о диске на сервере {server.name}</b>
Диск заполнен на <b>{usage_percent}%</b>
IP: {server.ip_address}
Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return TelegramManager.send_message(message)
    
    @staticmethod
    def send_ssl_expiration_warning(domain, days_left):
        """
        Отправляет предупреждение об истечении SSL сертификата
        
        Args:
            domain: объект Domain
            days_left: количество дней до истечения
            
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        message = f"""
<b>⚠️ Предупреждение об SSL сертификате</b>
Домен: <b>{domain.name}</b>
Сертификат истекает через <b>{days_left} дней</b>
Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return TelegramManager.send_message(message)
        
    @staticmethod
    def send_domain_check_warning(domain, error_message):
        """
        Отправляет предупреждение о проблемах с доменом
        
        Args:
            domain: объект Domain
            error_message: сообщение об ошибке
            
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        message = f"""
<b>⚠️ Проблема с доменом {domain.name}</b>
Ошибка: <b>{error_message}</b>
Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return TelegramManager.send_message(message)
    
    @staticmethod
    def send_debug_message(text):
        """
        Отправляет отладочное сообщение в Telegram
        
        Args:
            text: Текст сообщения
            
        Returns:
            bool: True в случае успеха, False в случае ошибки
        """
        message = f"""
<b>🔧 Отладочное сообщение</b>
{text}
Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return TelegramManager.send_message(message, disable_notification=True)