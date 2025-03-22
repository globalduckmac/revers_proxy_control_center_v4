import os
from datetime import datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
from config import config


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

# initialize the app with the extension
db.init_app(app)

# Add template globals
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

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
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(servers_bp)
    app.register_blueprint(domains_bp)
    app.register_blueprint(domain_groups_bp)
    app.register_blueprint(proxy_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(server_groups_bp, url_prefix='/server-groups')
    app.register_blueprint(users_bp)
    app.register_blueprint(settings_bp)

# Register template filters
from filters import register_filters
register_filters(app)

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
