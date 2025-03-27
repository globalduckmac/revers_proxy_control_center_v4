#!/bin/bash

# Скрипт быстрой установки Reverse Proxy Control Center v3
# Автоматическая установка с одной команды

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

# Генерация случайных паролей
generate_password() {
    < /dev/urandom tr -dc 'A-Za-z0-9!#$%&()*+,-./:;<=>?@[\]^_`{|}~' | head -c 18
}

# Проверяем, запущен ли скрипт от имени root
if [ "$EUID" -ne 0 ]; then
    error "Пожалуйста, запустите скрипт от имени администратора (sudo ./install.sh)"
fi

# Получаем IP-адрес сервера
SERVER_IP=$(hostname -I | awk '{print $1}')
ADMIN_PASSWORD=$(generate_password)
DB_PASSWORD=$(generate_password)
SESSION_SECRET=$(generate_password)

# Устанавливаем необходимые пакеты
info "Установка необходимых пакетов..."
apt-get update
apt-get install -y python3 python3-venv python3-dev build-essential libpq-dev postgresql postgresql-contrib nginx git

# Клонируем репозиторий, если запущена только команда wget
if [ ! -d "revers_proxy_control_center_v3" ] && [ ! -f "deploy_script.sh" ]; then
    info "Клонирование репозитория..."
    git clone https://github.com/globalduckmac/revers_proxy_control_center_v3.git
    cd revers_proxy_control_center_v3
else
    info "Используем текущую директорию..."
fi

# Переменные для конфигурации
APP_DIR="/opt/reverse_proxy_control_center"
APP_USER="rpcc"
APP_GROUP="rpcc"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="/var/log/reverse_proxy_control_center"
SYSTEMD_SERVICE="/etc/systemd/system/reverse_proxy_control_center.service"

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

# Копируем файлы проекта
info "Копирование файлов проекта..."
if [ -d "revers_proxy_control_center_v3" ]; then
    cp -r revers_proxy_control_center_v3/* $APP_DIR/
else
    # Если мы уже в директории проекта
    cp -r * $APP_DIR/
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
    sudo -u postgres psql -c "CREATE USER rpcc WITH PASSWORD '$DB_PASSWORD';"
    sudo -u postgres psql -c "ALTER ROLE rpcc SET client_encoding TO 'utf8';"
    sudo -u postgres psql -c "ALTER ROLE rpcc SET default_transaction_isolation TO 'read committed';"
    sudo -u postgres psql -c "ALTER ROLE rpcc SET timezone TO 'UTC';"
else
    info "Пользователь PostgreSQL rpcc уже существует, обновляем пароль..."
    sudo -u postgres psql -c "ALTER USER rpcc WITH PASSWORD '$DB_PASSWORD';"
fi

# Предоставляем привилегии пользователю
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE rpcc TO rpcc;"

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
Environment="SESSION_SECRET=$SESSION_SECRET"
Environment="DATABASE_URL=postgresql://rpcc:$DB_PASSWORD@localhost/rpcc"
ExecStart=$VENV_DIR/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Создаем администратора
info "Создание администратора..."
cd $APP_DIR
source $VENV_DIR/bin/activate

# Скрипт создания администратора
cat > create_admin_temp.py << EOL
from app import app, db
from models import User
from werkzeug.security import generate_password_hash
import sys

def create_admin():
    with app.app_context():
        # Проверяем, существует ли пользователь admin
        admin = User.query.filter_by(username='admin').first()
        
        if admin:
            print("Администратор уже существует. Обновляем пароль...")
            admin.password_hash = generate_password_hash("$ADMIN_PASSWORD")
        else:
            print("Создаем нового администратора...")
            admin = User(
                username='admin',
                email='admin@example.com',
                password_hash=generate_password_hash("$ADMIN_PASSWORD"),
                is_admin=True
            )
            db.session.add(admin)
        
        db.session.commit()
        print("Администратор успешно создан/обновлен!")
        return True

if __name__ == "__main__":
    success = create_admin()
    sys.exit(0 if success else 1)
EOL

# Выполняем скрипт создания администратора
sudo -u $APP_USER python create_admin_temp.py
rm create_admin_temp.py

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

# Перезапускаем systemd и включаем сервис
info "Запуск сервиса..."
systemctl daemon-reload
systemctl enable reverse_proxy_control_center
systemctl restart reverse_proxy_control_center

# Сохраняем учетные данные в файл
cat > /root/rpcc_credentials.txt << EOL
======================================================
REVERSE PROXY CONTROL CENTER - УЧЕТНЫЕ ДАННЫЕ
======================================================
URL: http://$SERVER_IP
Логин: admin
Пароль: $ADMIN_PASSWORD
======================================================
База данных PostgreSQL:
  - Имя базы: rpcc
  - Пользователь: rpcc
  - Пароль: $DB_PASSWORD
  - URL: postgresql://rpcc:$DB_PASSWORD@localhost/rpcc
======================================================
Секретный ключ сессии: $SESSION_SECRET
======================================================
Сохраните эту информацию в безопасном месте!
ЭТОТ ФАЙЛ БУДЕТ АВТОМАТИЧЕСКИ УДАЛЕН ЧЕРЕЗ 24 ЧАСА.
======================================================
EOL

chmod 600 /root/rpcc_credentials.txt

# Создаем задачу cron для удаления файла с учетными данными через 24 часа
(crontab -l 2>/dev/null; echo "$(date -d '24 hours' +'%M %H %d %m *') rm -f /root/rpcc_credentials.txt") | crontab -

# Вывод информации об установке
clear
echo "======================================================="
echo "УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!"
echo "======================================================="
echo "Reverse Proxy Control Center доступен по адресу:"
echo "  http://$SERVER_IP"
echo ""
echo "Данные для входа:"
echo "  Логин: admin"
echo "  Пароль: $ADMIN_PASSWORD"
echo ""
echo "Данные сохранены в файле /root/rpcc_credentials.txt"
echo "Файл будет автоматически удален через 24 часа."
echo "======================================================="
echo "Статус сервиса: $(systemctl is-active reverse_proxy_control_center)"
echo "======================================================="