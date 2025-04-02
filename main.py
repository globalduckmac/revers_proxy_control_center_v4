from app import app
import logging
import atexit
from flask import g, jsonify
import os
import asyncio

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Запускаем фоновые задачи
from tasks import background_tasks
from modules.telegram_notifier import TelegramNotifier

# Флаг, указывающий, были ли запущены фоновые задачи
background_tasks_started = False

# Проверяем настройки Telegram при старте приложения
from models import SystemSetting

# Используем контекст приложения для доступа к базе данных
with app.app_context():
    try:
        app.logger.info("Checking Telegram configuration")
        if TelegramNotifier.is_configured():
            app.logger.info("Telegram notifications are configured and ready to use")
            telegram_token = SystemSetting.get_value('telegram_bot_token')
            app.logger.info(f"Telegram bot token: {'*' * 10}{telegram_token[-5:] if telegram_token else 'Not set'}")
            app.logger.info(f"Telegram chat ID: {SystemSetting.get_value('telegram_chat_id')}")
        else:
            app.logger.warning("Telegram notifications are not configured! Add settings in the System Settings panel.")
    except Exception as e:
        app.logger.error(f"Error while checking Telegram configuration: {str(e)}")

# Добавляем тестовый маршрут для проверки конфигурации Telegram
@app.route('/debug/telegram-test')
def test_telegram_debug():
    """Тестовый маршрут для проверки работы Telegram уведомлений."""
    # Этот маршрут уже выполняется в контексте приложения Flask,
    # поэтому дополнительно создавать app_context не нужно
    
    if not TelegramNotifier.is_configured():
        try:
            telegram_token = SystemSetting.get_value('telegram_bot_token')
            telegram_chat_id = SystemSetting.get_value('telegram_chat_id')
            return jsonify({
                'status': 'error',
                'message': 'Telegram notifications are not configured',
                'token_exists': bool(telegram_token),
                'chat_id_exists': bool(telegram_chat_id),
            })
        except Exception as e:
            app.logger.error(f"Error accessing Telegram settings: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': f'Error accessing settings: {str(e)}',
                'token_exists': False,
                'chat_id_exists': False,
            })
    
    try:
        # Создаем тестовое сообщение
        test_message = f"""
🔍 <b>Отладочное сообщение</b>

Это сообщение отправлено через отладочный маршрут для проверки работы Telegram.
Время сервера: {asyncio.run(TelegramNotifier.get_current_time())}

<i>Если вы видите это сообщение, значит настройка Telegram выполнена корректно!</i>
"""
        # Создаем event loop и отправляем сообщение
        result = asyncio.run(TelegramNotifier.send_message(test_message))
        
        try:
            telegram_token = SystemSetting.get_value('telegram_bot_token')
            telegram_chat_id = SystemSetting.get_value('telegram_chat_id')
            
            return jsonify({
                'status': 'success' if result else 'error',
                'message': 'Test message sent successfully' if result else 'Failed to send message',
                'token_prefix': telegram_token[:5] + '...' if telegram_token else 'Not set',
                'chat_id': telegram_chat_id if telegram_chat_id else 'Not set',
            })
        except Exception as e:
            app.logger.error(f"Error accessing Telegram settings for response: {str(e)}")
            return jsonify({
                'status': 'success' if result else 'error',
                'message': 'Test message sent successfully' if result else 'Failed to send message',
                'token_error': str(e),
            })
    
    except Exception as e:
        app.logger.error(f"Error sending test Telegram message: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Exception occurred: {str(e)}',
            'error_type': str(type(e).__name__),
        })

@app.route('/debug/daily-report')
def test_daily_report():
    """Тестовый маршрут для отправки ежедневного отчета."""
    
    if not TelegramNotifier.is_configured():
        return jsonify({
            'status': 'error',
            'message': 'Telegram notifications are not configured'
        })
    
    try:
        # Отправляем ежедневный отчет
        asyncio.run(TelegramNotifier.send_daily_report())
        
        return jsonify({
            'status': 'success',
            'message': 'Daily report sent successfully'
        })
    
    except Exception as e:
        app.logger.error(f"Error sending daily report: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Exception occurred: {str(e)}',
            'error_type': str(type(e).__name__),
        })

# Запускаем задачи при первом запросе
@app.before_request
def start_background_tasks_if_needed():
    global background_tasks_started
    if not background_tasks_started:
        background_tasks.start()
        background_tasks_started = True
        app.logger.info("Background tasks started on first request")
        
        # Информируем о настроенных уведомлениях
        try:
            if TelegramNotifier.is_configured():
                app.logger.info("Telegram notifications are enabled for system events")
        except Exception as e:
            app.logger.error(f"Error checking Telegram configuration: {str(e)}")

# Останавливаем задачи при остановке приложения
atexit.register(background_tasks.stop)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
