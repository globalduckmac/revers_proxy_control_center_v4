from app import app
import logging
import atexit
from flask import g

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Запускаем фоновые задачи
from tasks import background_tasks

# Флаг, указывающий, были ли запущены фоновые задачи
background_tasks_started = False

# Запускаем задачи при первом запросе
@app.before_request
def start_background_tasks_if_needed():
    global background_tasks_started
    if not background_tasks_started:
        background_tasks.start()
        background_tasks_started = True
        app.logger.info("Background tasks started on first request")

# Останавливаем задачи при остановке приложения
atexit.register(background_tasks.stop)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
