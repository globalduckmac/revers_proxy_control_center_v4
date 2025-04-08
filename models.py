import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json
import logging
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from app import db

logger = logging.getLogger(__name__)


class User(UserMixin, db.Model):
    """Модель пользователя системы."""
    
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Server(db.Model):
    """Модель сервера."""
    
    __tablename__ = 'servers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)  # Поддержка IPv6
    ssh_port = db.Column(db.Integer, default=22)
    ssh_user = db.Column(db.String(64), nullable=False)
    ssh_password_hash = db.Column(db.String(256))  # Хешированный пароль
    ssh_key_path = db.Column(db.String(256))  # Путь к ключу
    ssh_encrypted_password = db.Column(db.LargeBinary)  # Зашифрованный пароль
    description = db.Column(db.Text)
    status = db.Column(db.String(32), default='unknown')  # unknown, active, inactive, error
    location = db.Column(db.String(128))
    provider = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    last_check = db.Column(db.DateTime)
    use_key_auth = db.Column(db.Boolean, default=False)
    config_path = db.Column(db.String(256), default='/etc/nginx/sites-available')
    config_enabled_path = db.Column(db.String(256), default='/etc/nginx/sites-enabled')
    ssl_certificates_path = db.Column(db.String(256), default='/etc/ssl')
    custom_commands = db.Column(db.Text)  # JSON-строка с пользовательскими командами
    
    # Поля для мониторинга
    cpu_usage = db.Column(db.Float)
    memory_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    load_average = db.Column(db.String(32))
    boot_time = db.Column(db.DateTime)
    
    # Поля для биллинга
    payment_date = db.Column(db.Date)
    next_payment_date = db.Column(db.Date)
    payment_amount = db.Column(db.Float)
    payment_currency = db.Column(db.String(3), default='USD')
    payment_status = db.Column(db.String(32), default='unknown')  # paid, pending, overdue
    comment = db.Column(db.Text)
    
    # Поля для Glances
    glances_installed = db.Column(db.Boolean, default=False)
    glances_enabled = db.Column(db.Boolean, default=False)
    glances_port = db.Column(db.Integer, default=61208)
    glances_protocol = db.Column(db.String(10), default='http')
    glances_status = db.Column(db.String(32), default='unknown')
    glances_last_check = db.Column(db.DateTime)
    
    # Отношения
    groups = db.relationship('ServerGroup', secondary='server_group_association', 
                             back_populates='servers')
    metrics = db.relationship('ServerMetric', backref='server', lazy='dynamic',
                             cascade='all, delete-orphan')
    logs = db.relationship('ServerLog', backref='server', lazy='dynamic',
                          cascade='all, delete-orphan')
    
    @property
    def domain_groups(self):
        """Возвращает группы доменов, связанные с сервером через группы серверов."""
        # Упрощенная реализация для устранения ошибок
        result = []
        server_group_ids = [group.id for group in self.groups]
        
        for group_id in server_group_ids:
            domain_groups = DomainGroupAssociation.query.filter_by(group_id=group_id).all()
            for dg in domain_groups:
                domain_group = DomainGroup.query.get(dg.group_id)
                if domain_group and domain_group not in result:
                    result.append(domain_group)
                    
        return result
    
    def get_ssh_password(self, master_password):
        """
        Расшифровывает пароль SSH с помощью мастер-пароля.
        
        Args:
            master_password: Мастер-пароль для расшифровки
            
        Returns:
            str: Расшифрованный пароль или None, если расшифровка не удалась
        """
        if not self.ssh_encrypted_password:
            return None
            
        try:
            # Генерируем ключ на основе мастер-пароля
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'static_salt_for_server_pwd',  # В реальной системе используйте уникальную соль
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
            
            # Создаем объект Fernet для расшифровки
            cipher_suite = Fernet(key)
            
            # Расшифровываем пароль
            decrypted_password = cipher_suite.decrypt(self.ssh_encrypted_password)
            return decrypted_password.decode()
            
        except Exception as e:
            logger.error(f"Error decrypting SSH password: {e}")
            return None
    
    def set_ssh_password(self, password, master_password):
        """
        Шифрует и сохраняет пароль SSH с помощью мастер-пароля.
        
        Args:
            password: Пароль SSH для шифрования
            master_password: Мастер-пароль для шифрования
            
        Returns:
            bool: True, если пароль успешно зашифрован, иначе False
        """
        try:
            # Генерируем ключ на основе мастер-пароля
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'static_salt_for_server_pwd',  # В реальной системе используйте уникальную соль
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
            
            # Создаем объект Fernet для шифрования
            cipher_suite = Fernet(key)
            
            # Шифруем пароль
            self.ssh_encrypted_password = cipher_suite.encrypt(password.encode())
            return True
            
        except Exception as e:
            logger.error(f"Error encrypting SSH password: {e}")
            return False
    
    def get_glances_url(self):
        """Возвращает URL для доступа к Glances API."""
        return f"{self.glances_protocol}://{self.ip_address}:{self.glances_port}"
    
    def __repr__(self):
        return f'<Server {self.name} ({self.ip_address})>'


class ServerGroup(db.Model):
    """Модель группы серверов."""
    
    __tablename__ = 'server_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Отношения
    servers = db.relationship('Server', secondary='server_group_association',
                             back_populates='groups')
    
    def __repr__(self):
        return f'<ServerGroup {self.name}>'


class ServerGroupAssociation(db.Model):
    """Таблица связи между серверами и группами серверов."""
    
    __tablename__ = 'server_group_association'
    
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'), primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('server_groups.id'), primary_key=True)


class Domain(db.Model):
    """Модель домена."""
    
    __tablename__ = 'domains'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    description = db.Column(db.Text)
    target_ip = db.Column(db.String(45))  # IP-адрес для направления трафика
    is_active = db.Column(db.Boolean, default=True)
    ssl_enabled = db.Column(db.Boolean, default=False)
    ssl_status = db.Column(db.String(32), default='unknown')  # unknown, valid, expired, error
    ssl_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    dns_record_type = db.Column(db.String(10), default='A')
    expected_nameservers = db.Column(db.Text)  # JSON-строка с ожидаемыми NS серверами
    ns_status = db.Column(db.String(32), default='unknown')  # unknown, ok, error
    monitoring_enabled = db.Column(db.Boolean, default=False)
    last_status = db.Column(db.String(32), default='unknown')  # unknown, up, down
    http_status_code = db.Column(db.Integer)
    response_time = db.Column(db.Float)  # Время ответа в миллисекундах
    last_check_time = db.Column(db.DateTime)
    
    # Поля для FFPanel интеграции
    ffpanel_enabled = db.Column(db.Boolean, default=False)
    ffpanel_profile_id = db.Column(db.Integer)
    ffpanel_status = db.Column(db.String(32), default='unknown')
    ffpanel_last_update = db.Column(db.DateTime)
    ffpanel_target_ip = db.Column(db.String(45))  # Отдельный IP для FFPanel
    
    # Отношения
    groups = db.relationship('DomainGroup', secondary='domain_group_association',
                           back_populates='domains')
    logs = db.relationship('DomainLog', backref='domain', lazy='dynamic',
                         cascade='all, delete-orphan')
    configs = db.relationship('ProxyConfig', backref='domain', lazy='dynamic',
                            cascade='all, delete-orphan')
    metrics = db.relationship('DomainMetric', backref='domain', lazy='dynamic',
                            cascade='all, delete-orphan')
    
    @property
    def servers(self):
        """Возвращает список серверов, связанных с доменом через группы."""
        # Упрощенная реализация для устранения ошибок
        result = []
        domain_group_ids = [group.id for group in self.groups]
        
        for group_id in domain_group_ids:
            server_groups = ServerGroupAssociation.query.filter_by(group_id=group_id).all()
            for sg in server_groups:
                server = Server.query.get(sg.server_id)
                if server and server not in result:
                    result.append(server)
                    
        return result
    
    def get_expected_nameservers(self):
        """Возвращает список ожидаемых NS-серверов из JSON-строки."""
        if not self.expected_nameservers:
            return []
        
        try:
            return json.loads(self.expected_nameservers)
        except Exception as e:
            logger.error(f"Error parsing expected nameservers for domain {self.name}: {e}")
            return []
    
    def set_expected_nameservers(self, nameservers):
        """Устанавливает список ожидаемых NS-серверов в JSON-строку."""
        try:
            self.expected_nameservers = json.dumps(nameservers)
        except Exception as e:
            logger.error(f"Error setting expected nameservers for domain {self.name}: {e}")
            return False
        return True
    
    def __repr__(self):
        return f'<Domain {self.name}>'


class DomainGroup(db.Model):
    """Модель группы доменов."""
    
    __tablename__ = 'domain_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Отношения
    domains = db.relationship('Domain', secondary='domain_group_association',
                            back_populates='groups')
    
    def __repr__(self):
        return f'<DomainGroup {self.name}>'


class DomainGroupAssociation(db.Model):
    """Таблица связи между доменами и группами доменов."""
    
    __tablename__ = 'domain_group_association'
    
    domain_id = db.Column(db.Integer, db.ForeignKey('domains.id'), primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('domain_groups.id'), primary_key=True)


class ProxyConfig(db.Model):
    """Модель конфигурации прокси для домена."""
    
    __tablename__ = 'proxy_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(db.Integer, db.ForeignKey('domains.id'))
    config_name = db.Column(db.String(255), nullable=False)
    config_type = db.Column(db.String(32), default='nginx')  # nginx, haproxy, etc.
    template_name = db.Column(db.String(255))
    port = db.Column(db.Integer, default=80)
    ssl_port = db.Column(db.Integer, default=443)
    target_port = db.Column(db.Integer, default=80)
    ssl_certificate_path = db.Column(db.String(255))
    ssl_key_path = db.Column(db.String(255))
    is_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    last_deployed = db.Column(db.DateTime)
    deploy_status = db.Column(db.String(32), default='not_deployed')  # not_deployed, success, error
    config_data = db.Column(db.Text)  # Сохраненная конфигурация
    extra_data = db.Column(db.Text)  # JSON с дополнительными параметрами конфигурации
    
    def __repr__(self):
        return f'<ProxyConfig {self.config_name} for {self.domain.name if self.domain else "unknown"}>'
    
    def get_extra_data(self):
        """Возвращает словарь с дополнительными параметрами конфигурации."""
        if not self.extra_data:
            return {}
        
        try:
            return json.loads(self.extra_data)
        except Exception as e:
            logger.error(f"Error parsing extra_data for proxy config {self.id}: {e}")
            return {}
    
    def set_extra_data(self, data):
        """Устанавливает дополнительные параметры конфигурации."""
        try:
            self.extra_data = json.dumps(data)
            return True
        except Exception as e:
            logger.error(f"Error setting extra_data for proxy config {self.id}: {e}")
            return False


class ServerMetric(db.Model):
    """Модель метрик сервера."""
    
    __tablename__ = 'server_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    cpu_usage = db.Column(db.Float)
    memory_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    load_avg_1 = db.Column(db.Float)
    load_avg_5 = db.Column(db.Float)
    load_avg_15 = db.Column(db.Float)
    network_rx = db.Column(db.BigInteger)  # Bytes received
    network_tx = db.Column(db.BigInteger)  # Bytes transmitted
    processes_total = db.Column(db.Integer)
    processes_running = db.Column(db.Integer)
    uptime = db.Column(db.BigInteger)  # Seconds
    metrics_data = db.Column(db.Text)  # JSON с полными данными мониторинга
    
    def __repr__(self):
        return f'<ServerMetric for {self.server.name if self.server else "unknown"} at {self.timestamp}>'


class DomainMetric(db.Model):
    """Модель метрик домена."""
    
    __tablename__ = 'domain_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(db.Integer, db.ForeignKey('domains.id'))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    status = db.Column(db.String(32))  # up, down, error
    response_time = db.Column(db.Float)  # Milliseconds
    http_status = db.Column(db.Integer)
    content_length = db.Column(db.Integer)
    ssl_valid = db.Column(db.Boolean)
    ssl_days_remaining = db.Column(db.Integer)
    
    def __repr__(self):
        return f'<DomainMetric for {self.domain.name if self.domain else "unknown"} at {self.timestamp}>'


class ServerLog(db.Model):
    """Модель логов сервера."""
    
    __tablename__ = 'server_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    action = db.Column(db.String(64))  # login, deploy, check, etc.
    status = db.Column(db.String(32))  # success, warning, error
    message = db.Column(db.Text)
    details = db.Column(db.Text)  # JSON с дополнительными деталями
    
    def __repr__(self):
        return f'<ServerLog for {self.server.name if self.server else "unknown"} at {self.timestamp}: {self.action}>'


class DomainLog(db.Model):
    """Модель логов домена."""
    
    __tablename__ = 'domain_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(db.Integer, db.ForeignKey('domains.id'))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    action = db.Column(db.String(64))  # deploy, check, etc.
    status = db.Column(db.String(32))  # success, warning, error
    message = db.Column(db.Text)
    details = db.Column(db.Text)  # JSON с дополнительными деталями
    
    def __repr__(self):
        return f'<DomainLog for {self.domain.name if self.domain else "unknown"} at {self.timestamp}: {self.action}>'


class SystemSetting(db.Model):
    """Модель настроек системы."""
    
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), nullable=False, unique=True)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    @classmethod
    def get_value(cls, key, default=None):
        """Получает значение настройки по ключу."""
        setting = cls.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @classmethod
    def set_value(cls, key, value, description=None):
        """Устанавливает значение настройки по ключу."""
        setting = cls.query.filter_by(key=key).first()
        
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = cls(key=key, value=value, description=description)
            db.session.add(setting)
        
        try:
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting system setting {key}: {e}")
            db.session.rollback()
            return False
    
    def __repr__(self):
        return f'<SystemSetting {self.key}>'


class ExternalServer(db.Model):
    """Модель внешнего сервера для мониторинга."""
    
    __tablename__ = 'external_servers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)  # Поддержка IPv6
    description = db.Column(db.Text)
    location = db.Column(db.String(128))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    last_check_time = db.Column(db.DateTime)
    last_status = db.Column(db.String(32), default='unknown')  # unknown, ok, warning, error
    
    # Последние метрики
    cpu_percent = db.Column(db.Float)
    memory_percent = db.Column(db.Float)
    disk_percent = db.Column(db.Float)
    load_avg_1 = db.Column(db.Float)
    load_avg_5 = db.Column(db.Float)
    load_avg_15 = db.Column(db.Float)
    
    # Настройки Glances API
    glances_port = db.Column(db.Integer, default=61208)
    glances_api_user = db.Column(db.String(64))
    glances_api_password = db.Column(db.String(64))
    
    # Отношения
    metrics = db.relationship('ExternalServerMetric', backref='server', lazy='dynamic',
                             cascade='all, delete-orphan')
    
    def get_glances_web_url(self):
        """Возвращает URL для доступа к веб-интерфейсу Glances."""
        return f"http://{self.ip_address}:{self.glances_port}"
    
    def get_glances_api_url(self):
        """Возвращает базовый URL для доступа к Glances API."""
        return f"http://{self.ip_address}:{self.glances_port}/api/3"
    
    def __repr__(self):
        return f'<ExternalServer {self.name} ({self.ip_address})>'


class ExternalServerMetric(db.Model):
    """Модель метрик внешнего сервера."""
    
    __tablename__ = 'external_server_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('external_servers.id'))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    cpu_percent = db.Column(db.Float)
    memory_percent = db.Column(db.Float)
    disk_percent = db.Column(db.Float)
    load_avg_1 = db.Column(db.Float)
    load_avg_5 = db.Column(db.Float)
    load_avg_15 = db.Column(db.Float)
    processes_total = db.Column(db.Integer)
    processes_running = db.Column(db.Integer)
    network_in_bytes = db.Column(db.BigInteger)
    network_out_bytes = db.Column(db.BigInteger)
    metrics_data = db.Column(db.Text)  # JSON с полными данными мониторинга
    
    def __repr__(self):
        return f'<ExternalServerMetric for {self.server.name if self.server else "unknown"} at {self.timestamp}>'


# Создаем функцию для инициализации сервисных учетных записей и настроек
def init_default_data():
    """Инициализирует начальные данные в базе."""
    
    # Проверяем, существует ли администратор
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        # Создаем учетную запись администратора
        admin = User(
            username='admin',
            email='admin@example.com',
            is_admin=True
        )
        admin.set_password('admin')  # В реальной системе используйте безопасный пароль
        db.session.add(admin)
        
        # Создаем начальные настройки
        settings = [
            ('smtp_host', '', 'SMTP-сервер для отправки уведомлений'),
            ('smtp_port', '587', 'Порт SMTP-сервера'),
            ('smtp_user', '', 'Имя пользователя SMTP'),
            ('smtp_password', '', 'Пароль SMTP'),
            ('smtp_from', 'notifications@example.com', 'Адрес отправителя'),
            ('telegram_bot_token', '', 'Токен бота Telegram для отправки уведомлений'),
            ('telegram_chat_id', '', 'ID чата Telegram для отправки уведомлений'),
            ('expected_ns_servers', 'dnspod', 'Ожидаемые NS-серверы для доменов (через запятую)'),
            ('check_server_interval', '300', 'Интервал проверки серверов (секунды)'),
            ('check_domain_interval', '3600', 'Интервал проверки доменов (секунды)'),
            ('high_cpu_threshold', '80', 'Порог высокой загрузки CPU (%)'),
            ('high_memory_threshold', '80', 'Порог высокой загрузки памяти (%)'),
            ('high_disk_threshold', '85', 'Порог высокой загрузки диска (%)'),
        ]
        
        for key, value, description in settings:
            setting = SystemSetting(key=key, value=value, description=description)
            db.session.add(setting)
        
        # Создаем группу серверов по умолчанию
        default_server_group = ServerGroup(name='Default', description='Группа серверов по умолчанию')
        db.session.add(default_server_group)
        
        # Создаем группу доменов по умолчанию
        default_domain_group = DomainGroup(name='Default', description='Группа доменов по умолчанию')
        db.session.add(default_domain_group)
        
        # Фиксируем изменения
        db.session.commit()
        logger.info("Initialized default data in the database")
    else:
        logger.info("Default data already exists in the database")


# Функция для получения всех отношений между доменами и серверами
def get_domain_server_relations():
    """
    Возвращает список всех отношений между доменами и серверами.
    
    Returns:
        list: Список кортежей (domain_id, server_id)
    """
    result = []
    
    # Упрощенная реализация для устранения ошибок с SQLAlchemy
    domains = Domain.query.all()
    for domain in domains:
        for server in domain.servers:
            result.append((domain.id, server.id))
            
    return result