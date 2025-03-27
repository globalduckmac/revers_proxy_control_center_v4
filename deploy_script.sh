#!/bin/bash

# Скрипт для развертывания Reverse Proxy Control Center v3
# Очищенная версия без MQTT и SSH-мониторинга доменов
# Используется только Glances API для мониторинга серверов

set -e

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Функция для вывода информации
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

# Функция для вывода предупреждений
warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Функция для вывода ошибок
error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Проверяем, запущен ли скрипт от имени root
if [ "$EUID" -ne 0 ]; then
    error "Пожалуйста, запустите скрипт от имени администратора (root)"
fi

# Определение переменных окружения
APP_DIR="/opt/reverse_proxy_control_center"
APP_USER="rpcc"
APP_GROUP="rpcc"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="/var/log/reverse_proxy_control_center"
SYSTEMD_SERVICE="/etc/systemd/system/reverse_proxy_control_center.service"

# Устанавливаем необходимые пакеты
info "Установка необходимых пакетов..."
apt-get update
apt-get install -y python3 python3-venv python3-dev build-essential libpq-dev postgresql postgresql-contrib nginx git

# Создаем пользователя для приложения, если он еще не существует
if ! id -u $APP_USER &>/dev/null; then
    info "Создаем пользователя $APP_USER..."
    useradd -m -s /bin/bash $APP_USER
else
    info "Пользователь $APP_USER уже существует"
fi

# Создаем директорию для приложения
info "Создаем директорию приложения..."
if [ ! -d "$APP_DIR" ]; then
    mkdir -p $APP_DIR
    chown $APP_USER:$APP_GROUP $APP_DIR
else
    info "Директория $APP_DIR уже существует"
fi

# Создаем директорию для логов
info "Создаем директорию для логов..."
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p $LOG_DIR
    chown $APP_USER:$APP_GROUP $LOG_DIR
else
    info "Директория для логов $LOG_DIR уже существует"
fi

# Клонируем репозиторий
info "Клонирование репозитория..."
if [ ! -d "$APP_DIR/.git" ]; then
    cd /opt
    rm -rf $APP_DIR/* 2>/dev/null || true
    git clone https://github.com/globalduckmac/revers_proxy_control_center_v3.git reverse_proxy_control_center
    chown -R $APP_USER:$APP_GROUP $APP_DIR
else
    cd $APP_DIR
    git pull
    chown -R $APP_USER:$APP_GROUP $APP_DIR
fi

# Создаем виртуальное окружение и устанавливаем зависимости
info "Настройка виртуального окружения Python..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv $VENV_DIR
    chown -R $APP_USER:$APP_GROUP $VENV_DIR
fi

# Активируем виртуальное окружение и устанавливаем зависимости
info "Установка зависимостей Python..."
cd $APP_DIR
source $VENV_DIR/bin/activate
pip install --upgrade pip
if [ -f "$APP_DIR/dependencies.txt" ]; then
    info "Установка зависимостей из файла dependencies.txt..."
    pip install -r "$APP_DIR/dependencies.txt"
else
    info "Файл dependencies.txt не найден, устанавливаем основные зависимости..."
    pip install psycopg2-binary cryptography dnspython email-validator flask flask-login flask-sqlalchemy flask-wtf glances gunicorn jinja2 paramiko python-telegram-bot pytz requests sqlalchemy werkzeug
fi

# Устанавливаем права на все файлы
chown -R $APP_USER:$APP_GROUP $APP_DIR

# Создаем systemd сервис
info "Создание systemd сервиса..."
cat > $SYSTEMD_SERVICE << EOL
[Unit]
Description=Reverse Proxy Control Center
After=network.target postgresql.service

[Service]
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
Environment="SESSION_SECRET=change_me_in_production"
Environment="DATABASE_URL=postgresql://rpcc:rpcc_password@localhost/rpcc"
ExecStart=$VENV_DIR/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Создаем и настраиваем базу данных PostgreSQL
info "Настройка базы данных PostgreSQL..."
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='rpcc'" | grep -q 1; then
    info "Создаем базу данных rpcc..."
    sudo -u postgres psql -c "CREATE DATABASE rpcc;"
else
    info "База данных rpcc уже существует"
fi

# Создаем пользователя PostgreSQL, если он не существует
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='rpcc'" | grep -q 1; then
    info "Создаем пользователя PostgreSQL rpcc..."
    sudo -u postgres psql -c "CREATE USER rpcc WITH PASSWORD 'rpcc_password';"
    sudo -u postgres psql -c "ALTER ROLE rpcc SET client_encoding TO 'utf8';"
    sudo -u postgres psql -c "ALTER ROLE rpcc SET default_transaction_isolation TO 'read committed';"
    sudo -u postgres psql -c "ALTER ROLE rpcc SET timezone TO 'UTC';"
else
    info "Пользователь PostgreSQL rpcc уже существует"
fi

# Предоставляем привилегии пользователю
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE rpcc TO rpcc;"

# Перезапускаем systemd и включаем сервис
info "Запуск сервиса..."
systemctl daemon-reload
systemctl enable reverse_proxy_control_center
systemctl restart reverse_proxy_control_center

# Настраиваем Nginx
info "Настройка Nginx..."
cat > /etc/nginx/sites-available/reverse_proxy_control_center << EOL
server {
    listen 80;
    server_name _;  # Замените на ваш домен

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias $APP_DIR/static;
    }
}
EOL

# Включаем конфигурацию Nginx
if [ ! -f /etc/nginx/sites-enabled/reverse_proxy_control_center ]; then
    ln -s /etc/nginx/sites-available/reverse_proxy_control_center /etc/nginx/sites-enabled/
fi

# Удаляем конфигурацию по умолчанию, если она существует
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm /etc/nginx/sites-enabled/default
fi

# Проверяем конфигурацию Nginx и перезапускаем
nginx -t && systemctl restart nginx

info "============================================"
info "Развертывание успешно завершено!"
info "Reverse Proxy Control Center доступен по адресу: http://your_server_ip"
info "============================================"
info "Дополнительная информация:"
info "- Systemd сервис: systemctl status reverse_proxy_control_center"
info "- Для просмотра логов: journalctl -u reverse_proxy_control_center -f"
info "- Директория приложения: $APP_DIR"
info "- Директория логов: $LOG_DIR"
info "============================================"
info "ВАЖНО: Для продакшена рекомендуется настроить следующее:"
info "1. Изменить секретный ключ SESSION_SECRET в $SYSTEMD_SERVICE"
info "2. Изменить пароль базы данных"
info "3. Настроить SSL-сертификат для Nginx (например, с помощью Let's Encrypt)"
info "4. Настроить регулярное резервное копирование базы данных"
info "5. Для работы уведомлений настройте переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID"
info "============================================"