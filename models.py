from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# Таблица связи между серверами и группами серверов
server_group_association = db.Table('server_group_association',
    db.Column('server_id', db.Integer, db.ForeignKey('server.id'), primary_key=True),
    db.Column('server_group_id', db.Integer, db.ForeignKey('server_group.id'), primary_key=True)
)

class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    ssh_port = db.Column(db.Integer, default=22)
    ssh_user = db.Column(db.String(64), nullable=False)
    ssh_key = db.Column(db.Text, nullable=True)  # SSH private key for authentication
    ssh_password_hash = db.Column(db.String(256), nullable=True)  # Hashed password storage
    status = db.Column(db.String(20), default='pending')  # pending, active, error
    last_check = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_ssh_password(self, password):
        """
        Хеширует и сохраняет пароль SSH с использованием werkzeug.security
        
        Args:
            password: Пароль в открытом виде
        """
        if password:
            self.ssh_password_hash = generate_password_hash(password)
        else:
            self.ssh_password_hash = None
            
    def check_ssh_password(self, password):
        """
        Проверяет соответствие пароля хешу
        
        Args:
            password: Пароль для проверки
            
        Returns:
            bool: True если пароль правильный, False в противном случае
        """
        if not self.ssh_password_hash:
            return False
        return check_password_hash(self.ssh_password_hash, password)
    
    @property
    def ssh_password(self):
        raise AttributeError('Пароль не хранится в открытом виде и не может быть прочитан')
        
    @ssh_password.setter
    def ssh_password(self, password):
        self.set_ssh_password(password)
    
    # Relationships
    domain_groups = db.relationship('DomainGroup', backref='server', lazy=True)
    logs = db.relationship('ServerLog', backref='server', lazy=True)
    # Связь многие-ко-многим с группами серверов
    groups = db.relationship('ServerGroup', secondary=server_group_association, 
                            backref=db.backref('servers', lazy='dynamic'))


class Domain(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    target_ip = db.Column(db.String(45), nullable=False)
    target_port = db.Column(db.Integer, default=80)
    ssl_enabled = db.Column(db.Boolean, default=False)
    ssl_status = db.Column(db.String(20), default='pending')  # pending, active, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Ожидаемые NS-записи, разделенные запятыми
    expected_nameservers = db.Column(db.Text, nullable=True)
    # Статус проверки NS: ok, mismatch, pending
    ns_status = db.Column(db.String(20), default='pending')
    # Фактические NS-записи, разделенные запятыми
    actual_nameservers = db.Column(db.Text, nullable=True)
    # Дата последней проверки NS
    ns_check_date = db.Column(db.DateTime, nullable=True)
    
    # Many-to-many relationship with DomainGroup
    groups = db.relationship('DomainGroup', secondary='domain_group_association', 
                            backref=db.backref('domains', lazy='dynamic'))


class DomainGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Association table for many-to-many relationship between Domain and DomainGroup
domain_group_association = db.Table('domain_group_association',
    db.Column('domain_id', db.Integer, db.ForeignKey('domain.id'), primary_key=True),
    db.Column('domain_group_id', db.Integer, db.ForeignKey('domain_group.id'), primary_key=True)
)


class ProxyConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    config_content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, deployed, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    server = db.relationship('Server', backref=db.backref('proxy_configs', lazy=True))


class ServerLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    action = db.Column(db.String(64), nullable=False)  # deploy, configure, check, etc.
    status = db.Column(db.String(20), nullable=False)  # success, error
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class ServerMetric(db.Model):
    """Stores monitoring metrics for servers."""
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('server.id'), nullable=False)
    cpu_usage = db.Column(db.Float, nullable=True)
    memory_usage = db.Column(db.Float, nullable=True)
    disk_usage = db.Column(db.Float, nullable=True)
    load_average = db.Column(db.String(30), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    server = db.relationship('Server', backref=db.backref('metrics', lazy=True))
    
class ServerGroup(db.Model):
    """Группы серверов для организации и фильтрации."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DomainMetric(db.Model):
    """Stores traffic metrics for domains."""
    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(db.Integer, db.ForeignKey('domain.id'), nullable=False)
    requests_count = db.Column(db.Integer, default=0)
    bandwidth_used = db.Column(db.BigInteger, default=0)  # in bytes
    avg_response_time = db.Column(db.Float, nullable=True)  # in milliseconds
    status_2xx_count = db.Column(db.Integer, default=0)
    status_3xx_count = db.Column(db.Integer, default=0)
    status_4xx_count = db.Column(db.Integer, default=0)
    status_5xx_count = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    domain = db.relationship('Domain', backref=db.backref('metrics', lazy=True))
