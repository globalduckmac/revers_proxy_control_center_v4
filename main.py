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
if TelegramNotifier.is_configured():
    app.logger.info("Telegram notifications are configured and ready to use")
    app.logger.info(f"Telegram bot token: {'*' * 10}{os.environ.get('TELEGRAM_BOT_TOKEN')[-5:] if os.environ.get('TELEGRAM_BOT_TOKEN') else 'Not set'}")
    app.logger.info(f"Telegram chat ID: {os.environ.get('TELEGRAM_CHAT_ID') if os.environ.get('TELEGRAM_CHAT_ID') else 'Not set'}")
else:
    app.logger.warning("Telegram notifications are not configured! Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.")

# Добавляем тестовый маршрут для проверки конфигурации Telegram
@app.route('/debug/telegram-test')
def test_telegram_debug():
    """Тестовый маршрут для проверки работы Telegram уведомлений."""
    if not TelegramNotifier.is_configured():
        return jsonify({
            'status': 'error',
            'message': 'Telegram notifications are not configured',
            'token_exists': bool(os.environ.get('TELEGRAM_BOT_TOKEN')),
            'chat_id_exists': bool(os.environ.get('TELEGRAM_CHAT_ID')),
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
        
        return jsonify({
            'status': 'success' if result else 'error',
            'message': 'Test message sent successfully' if result else 'Failed to send message',
            'token_prefix': os.environ.get('TELEGRAM_BOT_TOKEN')[:5] + '...' if os.environ.get('TELEGRAM_BOT_TOKEN') else 'Not set',
            'chat_id': os.environ.get('TELEGRAM_CHAT_ID') if os.environ.get('TELEGRAM_CHAT_ID') else 'Not set',
        })
    
    except Exception as e:
        app.logger.error(f"Error sending test Telegram message: {str(e)}")
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
        if TelegramNotifier.is_configured():
            app.logger.info("Telegram notifications are enabled for system events")

# Останавливаем задачи при остановке приложения
atexit.register(background_tasks.stop)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
