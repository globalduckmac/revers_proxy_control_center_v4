import os


class Config:
    """Base configuration class."""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'postgresql://rpcc:jidVLxKX5VihdK@localhost/rpcc')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Email for SSL certificates
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@example.com')

    # Nginx templates path
    NGINX_TEMPLATES_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'templates', 'nginx')
    # Default SSH settings
    DEFAULT_SSH_PORT = 22
    SSH_TIMEOUT = 60  # seconds
    # seconds for long-running commands (increased to 10 min for SSL setup)
    SSH_COMMAND_TIMEOUT = 600


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'sqlite:///dev.db')


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'sqlite:///test.db')


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
