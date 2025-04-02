import os

class Config:
    """Base configuration class."""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'mysql://root:password@localhost/reverse_proxy_manager')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Email for SSL certificates
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    
    # Nginx templates path
    NGINX_TEMPLATES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'nginx')
    
    # Default SSH settings
    DEFAULT_SSH_PORT = 22
    SSH_TIMEOUT = 60  # seconds
    SSH_COMMAND_TIMEOUT = 300  # seconds for long-running commands


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    """Production configuration."""
    # Production-specific settings
    pass


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
