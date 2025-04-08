import os

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
import datetime
import logging

logging.basicConfig(level=logging.INFO)

# Конфигурация логирования
logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()


# Функция для добавления now() в шаблоны
def inject_now():
    return {'now': datetime.datetime.utcnow()}


def register_blueprints(app):
    """Регистрирует все blueprint'ы приложения."""
    
    # Импортируем blueprint'ы
    from routes.auth import bp as auth_bp
    from routes.servers import bp as servers_bp
    from routes.domains import bp as domains_bp
    from routes.domain_groups import bp as domain_groups_bp
    from routes.proxy import bp as proxy_bp
    from routes.monitoring import bp as monitoring_bp
    from routes.settings import bp as settings_bp
    from routes.external_servers.routes import bp as external_servers_bp
    
    # Регистрируем blueprint'ы
    app.register_blueprint(auth_bp)
    app.register_blueprint(servers_bp)
    app.register_blueprint(domains_bp)
    app.register_blueprint(domain_groups_bp)
    app.register_blueprint(proxy_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(external_servers_bp)
    
    # Регистрация пользовательских фильтров
    from filters import register_filters
    register_filters(app)


def create_app(config_name='default'):
    """Создает и настраивает экземпляр приложения Flask."""
    
    app = Flask(__name__)
    
    # Загружаем конфигурацию
    if config_name == 'testing':
        from config import TestingConfig
        app.config.from_object(TestingConfig)
    elif config_name == 'production':
        from config import ProductionConfig
        app.config.from_object(ProductionConfig)
    else:
        from config import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)
    
    # Из переменных окружения (с приоритетом)
    app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', app.config.get('SECRET_KEY', 'dev-secret-key'))
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', app.config.get('SQLALCHEMY_DATABASE_URI'))
    
    # Инициализируем расширения
    db.init_app(app)
    login_manager.init_app(app)
    
    # Настраиваем login_manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
    login_manager.login_message_category = 'info'
    
    # Настройка загрузчика пользователя для Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))
    
    # Регистрируем context processors
    app.context_processor(inject_now)
    
    # Регистрируем blueprint'ы
    register_blueprints(app)
    
    # Регистрируем обработчики ошибок
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500
    
    # Создаем таблицы базы данных (если их нет)
    with app.app_context():
        try:
            db.create_all()
            logger.info("База данных инициализирована успешно")
        except Exception as e:
            logger.error(f"Ошибка при инициализации базы данных: {e}")
    
    # Настройка Telegram оповещений (если есть)
    with app.app_context():
        try:
            from models import SystemSetting
            
            telegram_token = SystemSetting.get_value('telegram_bot_token')
            telegram_chat_id = SystemSetting.get_value('telegram_chat_id')
            
            if telegram_token and telegram_chat_id:
                logger.info("Telegram notifications are configured and ready to use")
                logger.info(f"Telegram bot token: {'*'*10}{telegram_token[-5:]}")
                logger.info(f"Telegram chat ID: {telegram_chat_id}")
                app.config['TELEGRAM_NOTIFICATIONS_ENABLED'] = True
                app.config['TELEGRAM_BOT_TOKEN'] = telegram_token
                app.config['TELEGRAM_CHAT_ID'] = telegram_chat_id
            else:
                app.config['TELEGRAM_NOTIFICATIONS_ENABLED'] = False
                logger.warning("Telegram notifications are not configured")
        except Exception as e:
            logger.error(f"Ошибка при настройке Telegram оповещений: {e}")
            app.config['TELEGRAM_NOTIFICATIONS_ENABLED'] = False
    
    # Запуск фоновых задач (если не в режиме тестирования)
    if config_name != 'testing':
        logger.info("Skipping background tasks initialization in this version")
    
    # Настройка Telegram оповещений для системных событий
    if app.config.get('TELEGRAM_NOTIFICATIONS_ENABLED'):
        logger.info("Telegram notifications are enabled for system events")
        # Отправляем уведомление о запуске системы (раскомментируйте, если нужно)
        # send_system_notification("✅ Система управления запущена")
    
    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)