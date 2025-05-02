import os
import atexit
import asyncio
from datetime import datetime

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
from flask_socketio import SocketIO
from config import config
from filters import register_filters

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
# create the app
app = Flask(__name__)

# Load configuration
config_name = os.environ.get('FLASK_CONFIG', 'default')
app.config.from_object(config[config_name])

# Set secret key
app.secret_key = os.environ.get("SESSION_SECRET", app.config['SECRET_KEY'])

# Configure database connection pool
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Set up login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

socketio = SocketIO(app, cors_allowed_origins="*")

# initialize the app with the extension
db.init_app(app)

# Add template globals


@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}


@app.context_processor
def inject_spa_mode():
    """Add SPA mode detection to templates."""
    is_spa_request = request.headers.get('X-Requested-With') == \
        'XMLHttpRequest'
    return {'is_spa_request': is_spa_request}


@app.after_request
def after_request(response):
    """Handle AJAX requests for SPA."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if response.content_type == 'text/html; charset=utf-8':
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.data, 'html.parser')
            content = soup.find(id='spa-content')
            if content:
                return jsonify({
                    'title': soup.title.string if soup.title else '',
                    'content': str(content),
                    'url': request.url
                })
    return response


# Register blueprints


def register_blueprints(app):
    from routes.auth import bp as auth_bp
    from routes.servers import bp as servers_bp
    from routes.domains import bp as domains_bp
    from routes.domain_groups import bp as domain_groups_bp
    from routes.proxy import bp as proxy_bp
    from routes.monitoring import bp as monitoring_bp
    from routes.server_groups import server_groups_bp
    from routes.users import bp as users_bp
    from routes.settings import bp as settings_bp
    from routes.glances import bp as glances_bp
    from routes.external_servers import bp as external_servers_bp
    from routes.websockets import bp as websockets_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(servers_bp)
    app.register_blueprint(domains_bp)
    app.register_blueprint(domain_groups_bp)
    app.register_blueprint(proxy_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(server_groups_bp, url_prefix='/server-groups')
    app.register_blueprint(users_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(glances_bp)
    app.register_blueprint(external_servers_bp, url_prefix='/external-servers')
    app.register_blueprint(websockets_bp, url_prefix='/ws')


# Register template filters

register_filters(app)


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    app.logger.info("Client connected: {}".format(request.sid))


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    app.logger.info("Client disconnected: {}".format(request.sid))


@socketio.on('ssl_setup')
def handle_ssl_setup(data):
    """Handle SSL setup WebSocket event."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return {'status': 'error', 'message': 'Authentication required'}

    socketio.start_background_task(
        ssl_setup_task,
        data.get('server_id'),
        data.get('domain_id'),
        request.sid
    )

    return {'status': 'started', 'message': 'SSL setup started'}


def ssl_setup_task(server_id, domain_id, sid):
    """Background task for SSL setup."""
    from models import Server, Domain
    from modules.deployment import DeploymentManager

    with app.app_context():
        try:
            server = Server.query.get(server_id)
            domain = Domain.query.get(domain_id)

            if not server or not domain:
                socketio.emit('ssl_setup_update', {
                    'status': 'error',
                    'message': 'Server or domain not found'
                }, to=sid)
                return

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            class WebSocketWrapper:
                async def send_json(self, data):
                    socketio.emit('ssl_setup_update', data, to=sid)

            result = loop.run_until_complete(
                DeploymentManager.async_setup_ssl_certbot(
                    server,
                    domain,
                    WebSocketWrapper()
                )
            )

            loop.close()

            socketio.emit('ssl_setup_complete', {
                'status': 'success' if result else 'error',
                'message': ('SSL setup completed' if result
                            else 'SSL setup failed')
            }, to=sid)

        except Exception as e:
            app.logger.error("Error in SSL setup task: {}".format(str(e)))
            socketio.emit('ssl_setup_update', {
                'status': 'error',
                'message': 'Error: {}'.format(str(e))
            }, to=sid)


with app.app_context():
    # Import models to ensure they're registered with SQLAlchemy
    import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))

    # Create database tables if they don't exist
    db.create_all()

    # Register blueprints
    register_blueprints(app)


def cleanup_async_resources():
    """Clean up asyncio resources on application shutdown."""
    from modules.async_server_manager import AsyncServerManager
    import logging
    logger = logging.getLogger(__name__)

    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if not loop.is_closed():
            loop.run_until_complete(AsyncServerManager.close_all_connections())
    except Exception as e:
        logger.error("Error cleaning up async resources: {}".format(str(e)))


# Register cleanup function
atexit.register(cleanup_async_resources)
