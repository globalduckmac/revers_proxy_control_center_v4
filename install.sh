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
    pip install psycopg2-binary cryptography dnspython email-validator flask flask-login flask-sqlalchemy flask-wtf "glances>=4.3.1" gunicorn jinja2 paramiko python-telegram-bot pytz requests sqlalchemy werkzeug
fi

# Проверяем наличие файла main.py
if [ ! -f "$APP_DIR/main.py" ]; then
    error "Файл main.py не найден в директории $APP_DIR. Пожалуйста, проверьте, что репозиторий клонирован корректно."
fi

# Проверяем требуемые файлы
info "Проверка необходимых файлов и директорий..."
for required_file in "app.py" "main.py" "models.py" "config.py"; do
    if [ ! -f "$APP_DIR/$required_file" ]; then
        warn "Файл $required_file не найден! Приложение может работать некорректно."
    fi
done

# Проверяем директории
for required_dir in "templates" "static" "modules" "routes"; do
    if [ ! -d "$APP_DIR/$required_dir" ]; then
        warn "Директория $required_dir не найдена! Приложение может работать некорректно."
    fi
done

# Устанавливаем права на все файлы
chown -R $APP_USER:$APP_GROUP $APP_DIR
chmod -R 755 $APP_DIR

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
ExecStart=$VENV_DIR/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 120 --access-logfile $LOG_DIR/access.log --error-logfile $LOG_DIR/error.log main:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

# Создаем директорию для переопределений systemd
mkdir -p /etc/systemd/system/reverse_proxy_control_center.service.d/
cat > /etc/systemd/system/reverse_proxy_control_center.service.d/override.conf << EOL
[Service]
# Увеличиваем лимиты
LimitNOFILE=65536
# Добавляем задержку перед запуском для уверенности, что PostgreSQL полностью готов
ExecStartPre=/bin/sleep 2
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
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;  # Замените на ваш домен
    
    # Логи
    access_log /var/log/nginx/rpcc_access.log;
    error_log /var/log/nginx/rpcc_error.log;

    # Основные настройки
    client_max_body_size 50m;
    
    # Таймауты для лучшей совместимости с долгими запросами
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Параметры WebSocket (если используются)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Буферизация ответов
        proxy_buffering on;
        proxy_buffer_size 8k;
        proxy_buffers 8 8k;
    }

    location /static {
        alias $APP_DIR/static;
        expires 7d;
        add_header Cache-Control "public";
    }
    
    # Статус Nginx для мониторинга
    location /nginx_status {
        stub_status on;
        access_log off;
        allow 127.0.0.1;  # Разрешить доступ только с localhost
        deny all;         # Запретить все остальные
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

# Добавляем инструмент проверки и диагностики
cat > /usr/local/bin/rpcc-diagnose << 'EOL'
#!/bin/bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Диагностика Reverse Proxy Control Center${NC}"
echo -e "========================================"

# Проверка статуса сервисов
echo -e "\n${GREEN}Проверка статуса сервисов:${NC}"
echo -e "--------------------------------------"
systemctl is-active --quiet postgresql && echo -e "PostgreSQL: ${GREEN}активен${NC}" || echo -e "PostgreSQL: ${RED}не активен${NC}"
systemctl is-active --quiet nginx && echo -e "Nginx: ${GREEN}активен${NC}" || echo -e "Nginx: ${RED}не активен${NC}"
systemctl is-active --quiet reverse_proxy_control_center && echo -e "RPCC: ${GREEN}активен${NC}" || echo -e "RPCC: ${RED}не активен${NC}"

# Проверка работы портов
echo -e "\n${GREEN}Проверка сетевых портов:${NC}"
echo -e "--------------------------------------"
nc -z -v -w1 localhost 5000 2>/dev/null && echo -e "Порт 5000 (Gunicorn): ${GREEN}открыт${NC}" || echo -e "Порт 5000 (Gunicorn): ${RED}закрыт${NC}"
nc -z -v -w1 localhost 80 2>/dev/null && echo -e "Порт 80 (Nginx): ${GREEN}открыт${NC}" || echo -e "Порт 80 (Nginx): ${RED}закрыт${NC}"
nc -z -v -w1 localhost 5432 2>/dev/null && echo -e "Порт 5432 (PostgreSQL): ${GREEN}открыт${NC}" || echo -e "Порт 5432 (PostgreSQL): ${RED}закрыт${NC}"

# Проверка логов
echo -e "\n${GREEN}Последние ошибки в логах:${NC}"
echo -e "--------------------------------------"
echo -e "${YELLOW}Логи RPCC:${NC}"
if [ -f "/var/log/reverse_proxy_control_center/error.log" ]; then
    tail -n 5 /var/log/reverse_proxy_control_center/error.log
else
    echo "Лог-файл не найден"
fi

echo -e "\n${YELLOW}Логи Nginx:${NC}"
if [ -f "/var/log/nginx/rpcc_error.log" ]; then
    tail -n 5 /var/log/nginx/rpcc_error.log
else
    echo "Лог-файл не найден"
fi

echo -e "\n${YELLOW}Логи PostgreSQL:${NC}"
if [ -f "/var/log/postgresql/postgresql-$(psql --version | head -n 1 | awk '{print $3}' | cut -d. -f1-2)-main.log" ]; then
    tail -n 5 "/var/log/postgresql/postgresql-$(psql --version | head -n 1 | awk '{print $3}' | cut -d. -f1-2)-main.log"
else
    echo "Лог-файл не найден"
fi

# Проверка базы данных
echo -e "\n${GREEN}Проверка базы данных:${NC}"
echo -e "--------------------------------------"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='rpcc'" | grep -q 1; then
    echo -e "База данных 'rpcc': ${GREEN}существует${NC}"
else
    echo -e "База данных 'rpcc': ${RED}не существует${NC}"
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='rpcc'" | grep -q 1; then
    echo -e "Пользователь БД 'rpcc': ${GREEN}существует${NC}"
else
    echo -e "Пользователь БД 'rpcc': ${RED}не существует${NC}"
fi

# Советы по устранению неполадок
echo -e "\n${GREEN}Рекомендации по устранению неполадок:${NC}"
echo -e "--------------------------------------"
echo -e "1. Перезапустить сервисы: systemctl restart reverse_proxy_control_center nginx postgresql"
echo -e "2. Проверить полные логи: journalctl -u reverse_proxy_control_center -n 50"
echo -e "3. Проверить конфигурацию Nginx: nginx -t"
echo -e "4. Проверить разрешения файлов: ls -la /opt/reverse_proxy_control_center"
echo -e "5. Если проблемы сохраняются, выполните полную переустановку."
EOL

chmod +x /usr/local/bin/rpcc-diagnose

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
echo ""
echo "Если возникнут проблемы, выполните команду:"
echo "  sudo rpcc-diagnose"
echo "======================================================="

# Проверяем доступность веб-приложения
echo "Выполняем проверку доступности веб-приложения..."
sleep 5
# Проверка через curl
if curl -s http://localhost -o /dev/null; then
    echo -e "\n${GREEN}[УСПЕХ]${NC} Веб-приложение доступно! Сервер успешно запущен."
else
    echo -e "\n${YELLOW}[ПРЕДУПРЕЖДЕНИЕ]${NC} Веб-приложение пока недоступно."
    echo "Запускаем диагностику..."
    /usr/local/bin/rpcc-diagnose
    
    echo -e "\n${YELLOW}[СОВЕТ]${NC} Если веб-приложение недоступно, возможно, ему требуется больше времени для запуска."
    echo "Проверьте статус через несколько минут: systemctl status reverse_proxy_control_center"
fi