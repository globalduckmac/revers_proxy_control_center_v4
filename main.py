from app import app
import logging
import atexit
from flask import g
import os

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
