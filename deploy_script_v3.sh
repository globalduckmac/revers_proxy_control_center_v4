#!/bin/bash

# Полный скрипт деплоя для проекта Revers Proxy Control Center V3
# Этот скрипт выполняет:
# 1. Установку всех зависимостей
# 2. Настройку базы данных PostgreSQL
# 3. Настройку виртуального окружения Python
# 4. Обновление кода из репозитория
# 5. Настройку и запуск сервиса systemd

# Выход при любой ошибке
set -e

REPO_URL="https://github.com/globalduckmac/revers_proxy_control_center_v3.git"
INSTALL_DIR="/opt/reverse_proxy_manager"
APP_USER="webadmin"
APP_GROUP="webadmin"
VENV_DIR="$INSTALL_DIR/venv"
CONFIG_FILE="$INSTALL_DIR/config.py"
SERVICE_NAME="reverse_proxy_manager"
LOG_DIR="/var/log/reverse_proxy_manager"
ADMIN_EMAIL="admin@example.com"
ADMIN_PASSWORD="admin123"
START_ON_BOOT=true
DATABASE_NAME="reverse_proxy_manager"
DATABASE_USER="reverse_proxy_manager"

# Цветовое оформление
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
    exit 1
}

# Вывод заголовка
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}               Reverse Proxy Manager Installer              ${NC}"
echo -e "${BLUE}                     Версия: v3.0.0                         ${NC}"
echo -e "${BLUE}============================================================${NC}"
echo

# Проверка root прав
if [ "$EUID" -ne 0 ]; then
    error "Установка должна выполняться с правами root. Запустите скрипт с sudo."
fi

# Проверка и обновление пакетов
log "Обновление списка пакетов..."
apt-get update || error "Не удалось обновить список пакетов"

# Установка базовых зависимостей
log "Установка базовых зависимостей..."
apt-get install -y python3 python3-venv python3-pip python3-dev git nginx postgresql postgresql-contrib libpq-dev build-essential curl gnupg2 ssl-cert net-tools supervisor || error "Не удалось установить базовые зависимости"

# Создание пользователя и группы, если они еще не существуют
log "Создание системного пользователя для запуска приложения..."
id -u $APP_USER &>/dev/null || useradd -m -s /bin/bash $APP_USER
id -g $APP_GROUP &>/dev/null || groupadd $APP_GROUP

# Создание директорий
log "Создание директорий..."
mkdir -p $INSTALL_DIR
mkdir -p $LOG_DIR
chown -R $APP_USER:$APP_GROUP $LOG_DIR

# Настройка PostgreSQL
log "Настройка базы данных PostgreSQL..."
# Проверка, существует ли юзер и БД
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DATABASE_USER'" | grep -q 1; then
    log "Создание пользователя PostgreSQL..."
    sudo -u postgres psql -c "CREATE USER $DATABASE_USER WITH PASSWORD '$DATABASE_USER';"
fi

if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw $DATABASE_NAME; then
    log "Создание базы данных PostgreSQL..."
    sudo -u postgres psql -c "CREATE DATABASE $DATABASE_NAME WITH OWNER $DATABASE_USER;"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DATABASE_NAME TO $DATABASE_USER;"
fi

# Клонирование или обновление репозитория
if [ -d "$INSTALL_DIR/.git" ]; then
    log "Обновление кода из репозитория..."
    cd $INSTALL_DIR
    git pull
else
    log "Клонирование репозитория..."
    rm -rf $INSTALL_DIR
    git clone $REPO_URL $INSTALL_DIR
    cd $INSTALL_DIR
fi

# Настройка владельца директории установки
chown -R $APP_USER:$APP_GROUP $INSTALL_DIR

# Создание и активация виртуального окружения
log "Настройка виртуального окружения Python..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv $VENV_DIR
fi

# Установка зависимостей Python
log "Установка зависимостей Python..."
$VENV_DIR/bin/pip install --upgrade pip
$VENV_DIR/bin/pip install -r $INSTALL_DIR/requirements.txt || $VENV_DIR/bin/pip install gunicorn flask flask-sqlalchemy flask-login psycopg2-binary python-telegram-bot flask-wtf pymysql dnspython email-validator cryptography paramiko

# Установка Glances (добавлено в v3)
log "Установка и настройка Glances..."
apt-get install -y glances

# Создание systemd сервиса для Glances (если файл не существует)
if [ ! -f /etc/systemd/system/glances.service ]; then
    log "Создание systemd сервиса для Glances..."
    
    # Определяем путь к исполняемому файлу glances
    GLANCES_EXEC=$(which glances)
    
    cat << EOF > /etc/systemd/system/glances.service
[Unit]
Description=Glances Server
After=network.target

[Service]
ExecStart=$GLANCES_EXEC -w --port 61208 --disable-plugin sensors --enable-history
Restart=on-failure
Type=simple
User=root

[Install]
WantedBy=multi-user.target
EOF
    
    chmod 644 /etc/systemd/system/glances.service
    systemctl daemon-reload
    systemctl enable glances.service
    systemctl restart glances.service
    
    success "Glances настроен и запущен на порту 61208"
else
    log "Systemd сервис для Glances уже существует, перезапуск..."
    systemctl restart glances.service
fi

# Создание systemd сервиса
log "Создание systemd сервиса..."
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Reverse Proxy Manager
After=network.target postgresql.service

[Service]
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/gunicorn --bind 0.0.0.0:5000 --workers 4 main:app
Restart=always
Environment="PATH=$VENV_DIR/bin"
Environment="DATABASE_URL=postgresql://$DATABASE_USER:$DATABASE_USER@localhost/$DATABASE_NAME"
Environment="SESSION_SECRET=$(openssl rand -hex 32)"

[Install]
WantedBy=multi-user.target
EOF

# Перезагрузка systemd и запуск сервиса
log "Перезагрузка systemd и запуск сервиса..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME.service
systemctl restart $SERVICE_NAME.service

# Настройка Nginx
log "Настройка Nginx..."
cat > /etc/nginx/sites-available/$SERVICE_NAME << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Активация сайта Nginx
log "Активация сайта Nginx..."
ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

# Создание административного пользователя
log "Создание административного пользователя..."
cd $INSTALL_DIR && sudo -u $APP_USER $VENV_DIR/bin/python3 create_admin.py

# Проверка статуса сервисов
log "Проверка статуса сервисов..."
systemctl status $SERVICE_NAME --no-pager || warning "Сервис $SERVICE_NAME не запущен!"
systemctl status nginx --no-pager || warning "Сервис nginx не запущен!"
systemctl status glances --no-pager || warning "Сервис glances не запущен!"

# Проверка доступности веб-интерфейса
log "Проверка доступности веб-интерфейса..."
if curl -s http://localhost:5000 >/dev/null; then
    success "Веб-интерфейс доступен по адресу http://localhost:5000"
else
    warning "Веб-интерфейс недоступен! Проверьте журналы."
fi

# Проверка доступности Glances API
log "Проверка доступности Glances API..."
if curl -s http://localhost:61208/api/4/cpu >/dev/null; then
    success "Glances API доступен по адресу http://localhost:61208"
else
    warning "Glances API недоступен! Проверьте журналы systemd."
fi

success "Установка Reverse Proxy Manager завершена успешно!"
echo
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}              Установка успешно завершена!                  ${NC}"
echo -e "${GREEN}------------------------------------------------------------${NC}"
echo -e "${GREEN} URL админ-панели: http://$(hostname -I | awk '{print $1}'):80 ${NC}"
echo -e "${GREEN} Логин: admin@example.com                                  ${NC}"
echo -e "${GREEN} Пароль: admin123                                          ${NC}"
echo -e "${GREEN}============================================================${NC}"
echo

exit 0