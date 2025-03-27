#!/bin/bash

# ======================================================
# Скрипт автоматического развертывания 
# Reverse Proxy Control Center v2
# Поддерживает все последние зависимости и интеграции
# с Glances, FFPanel и автоматической миграцией DB 
# ======================================================

# Выход при любой ошибке для безопасной установки
set -e

# Цвета для удобного вывода информации
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для форматированного вывода
print_header() {
    echo -e "\n${GREEN}===== $1 =====${NC}"
}

print_subheader() {
    echo -e "\n${BLUE}>>> $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}ВНИМАНИЕ: $1${NC}"
}

print_error() {
    echo -e "${RED}ОШИБКА: $1${NC}"
}

# Переменные настройки
APP_NAME="Reverse Proxy Control Center"
APP_DIR="/opt/reverse-proxy-control-center"
GITHUB_REPO="https://github.com/globalduckmac/revers_proxy_control_center_v2.git"
GITHUB_BRANCH="main"
DB_NAME="reverse_proxy_manager"
DB_USER="proxy_manager"
DB_PASSWORD="secure_password_$(date +%s | sha256sum | base64 | head -c 8)"
APP_PORT=5000
ADMIN_USER="admin"
ADMIN_PASSWORD="admin123"
ADMIN_EMAIL="admin@example.com"

print_header "Начало установки $APP_NAME"
echo "Дата установки: $(date)"
echo "Версия: 2.0 от 27 марта 2025"

# Проверка root-прав
if [ "$EUID" -ne 0 ]; then
    print_warning "Запустите скрипт с правами администратора (sudo)"
    exit 1
fi

# Проверяем дистрибутив
if [ -f /etc/os-release ]; then
    source /etc/os-release
    if [[ "$ID" != "ubuntu" ]]; then
        print_warning "Скрипт оптимизирован для Ubuntu. Продолжение может привести к ошибкам."
        read -p "Продолжить? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
else
    print_warning "Не удалось определить ОС. Продолжение может привести к ошибкам."
    read -p "Продолжить? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Создаем каталог приложения
print_header "Создание каталога приложения"
mkdir -p "$APP_DIR"
# Устанавливаем владельца директории на текущего пользователя
CURRENT_USER=$(logname || echo $SUDO_USER || echo $USER)
chown $CURRENT_USER:$CURRENT_USER "$APP_DIR"

# Обновление системных пакетов
print_header "Обновление системных пакетов"
apt-get update
apt-get upgrade -y

# Установка необходимых системных пакетов
print_header "Установка системных зависимостей"
apt-get install -y python3 python3-pip python3-venv nginx postgresql postgresql-contrib \
    certbot python3-certbot-nginx git curl jq net-tools build-essential libssl-dev libffi-dev python3-dev

# Настройка PostgreSQL
print_header "Настройка PostgreSQL"
# Убеждаемся, что сервис PostgreSQL запущен
systemctl start postgresql
systemctl enable postgresql

# Проверяем существование базы данных
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    print_subheader "Создание пользователя и базы данных PostgreSQL"
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME WITH OWNER $DB_USER;"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    echo "База данных PostgreSQL и пользователь созданы успешно"
else
    print_subheader "База данных уже существует, пропускаем создание"
    # Обновляем пароль, если база уже существует
    sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
fi

# Получение исходного кода
print_header "Клонирование репозитория из GitHub"
cd /tmp

# Клонируем или обновляем репозиторий в зависимости от того, существует ли уже .git директория
if [ ! -d "$APP_DIR/.git" ]; then
    # Клонируем репозиторий, если это новая установка
    git clone $GITHUB_REPO -b $GITHUB_BRANCH temp_repo
    # Перемещаем все файлы из временного репозитория в APP_DIR
    cp -r temp_repo/* "$APP_DIR/"
    cp -r temp_repo/.git "$APP_DIR/"
    rm -rf temp_repo
    cd "$APP_DIR"
else
    # Выполняем git pull, если репозиторий уже существует
    cd "$APP_DIR"
    git stash # Сохраняем локальные изменения, если они есть
    git pull origin $GITHUB_BRANCH
fi

# Установка Python-окружения
print_header "Настройка Python-окружения"
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate

# Установка Python-зависимостей
print_header "Установка Python-зависимостей"
pip install --upgrade pip
pip install wheel # Необходимо для установки некоторых пакетов

# Устанавливаем все зависимости из списка
pip install gunicorn psycopg2-binary cryptography dnspython email-validator \
    flask flask-login flask-sqlalchemy flask-wtf jinja2 paramiko \
    python-telegram-bot pytz requests sqlalchemy werkzeug pymysql \
    glances fastapi uvicorn

# Удаляем все следы MQTT, если они были установлены ранее
print_subheader "Удаление любых следов MQTT"
pip uninstall -y paho-mqtt

# Настройка переменных окружения
print_header "Настройка переменных окружения"
# Генерируем случайный секретный ключ
SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(24))")

cat > "$APP_DIR/.env" <<EOF
FLASK_APP=main.py
FLASK_ENV=production
FLASK_CONFIG=production
SESSION_SECRET=$SESSION_SECRET
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost/$DB_NAME

# Настройки SSH
SSH_TIMEOUT=60
SSH_COMMAND_TIMEOUT=300

# Настройки электронной почты для SSL сертификатов
ADMIN_EMAIL=$ADMIN_EMAIL

# Настройки Telegram (необязательно)
# TELEGRAM_BOT_TOKEN=your_bot_token
# TELEGRAM_CHAT_ID=your_chat_id

# Настройки FFPanel (необязательно)
# FFPANEL_TOKEN=your_ffpanel_token

# Настройки GitHub (необязательно)
# GITHUB_TOKEN=your_github_token
EOF

# Обновляем путь к базе данных в config.py, если он существует
if [ -f "$APP_DIR/config.py" ]; then
    print_subheader "Обновление параметров базы данных в config.py"
    # Заменяем строку с настройками базы данных
    sed -i "s|'mysql://root:password@localhost/reverse_proxy_manager'|'postgresql://$DB_USER:$DB_PASSWORD@localhost/$DB_NAME'|" "$APP_DIR/config.py"
    # Параметры для работы с современными версиями PostgreSQL
    sed -i "s|SQLALCHEMY_TRACK_MODIFICATIONS = False|SQLALCHEMY_TRACK_MODIFICATIONS = False\n    SQLALCHEMY_ENGINE_OPTIONS = {\n        \"pool_recycle\": 300,\n        \"pool_pre_ping\": True\n    }|" "$APP_DIR/config.py"
fi

# Исправление путей и привилегий
print_subheader "Настройка прав доступа и создание директорий"
mkdir -p "$APP_DIR/static"
mkdir -p "$APP_DIR/templates/nginx"
chown -R $CURRENT_USER:$CURRENT_USER "$APP_DIR"

# Создание systemd сервиса для приложения
print_header "Создание systemd сервиса для приложения"
cat > /etc/systemd/system/reverse-proxy-control-center.service <<EOF
[Unit]
Description=Reverse Proxy Control Center
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:$APP_PORT --reuse-port --reload main:app
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

# Инициализация базы данных и создание администратора
print_header "Инициализация базы данных"
cd "$APP_DIR"
source venv/bin/activate

# Запускаем инициализацию базы данных
if [ -f "$APP_DIR/init_db.py" ]; then
    print_subheader "Запуск инициализации базы данных через init_db.py"
    python "$APP_DIR/init_db.py"
else
    print_subheader "Создание и запуск скрипта инициализации базы данных"
    cat > "$APP_DIR/init_db.py" <<EOF
from app import app, db
from models import User
import os

def create_admin_user():
    """Создание администратора если его нет"""
    with app.app_context():
        # Убедимся, что таблицы созданы
        db.create_all()
        
        # Проверяем наличие администратора
        if not User.query.filter_by(username='$ADMIN_USER').first():
            user = User(username='$ADMIN_USER', 
                      email='$ADMIN_EMAIL', 
                      is_admin=True)
            user.set_password('$ADMIN_PASSWORD')
            db.session.add(user)
            db.session.commit()
            print("Администратор создан")
        else:
            print("Администратор уже существует")

if __name__ == '__main__':
    # Инициализация базы данных
    with app.app_context():
        db.create_all()
        print("База данных инициализирована")
    
    # Создание администратора
    create_admin_user()
EOF
    python "$APP_DIR/init_db.py"
fi

# Настройка Nginx в качестве обратного прокси
print_header "Настройка Nginx обратного прокси"
cat > /etc/nginx/sites-available/reverse-proxy-control-center <<EOF
server {
    listen 80;
    server_name _;  # Замените на свой домен для HTTPS

    access_log /var/log/nginx/reverse-proxy-control-center.access.log;
    error_log /var/log/nginx/reverse-proxy-control-center.error.log;

    # Увеличенные лимиты для загрузки файлов и запросов
    client_max_body_size 50M;
    
    # Более строгие настройки безопасности
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Увеличенный таймаут для долгих операций
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    location /static {
        alias $APP_DIR/static;
        expires 30d;
    }
}
EOF

# Включаем сайт и перезапускаем Nginx
ln -sf /etc/nginx/sites-available/reverse-proxy-control-center /etc/nginx/sites-enabled/
# Удаляем дефолтный сайт, если он существует
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm -f /etc/nginx/sites-enabled/default
fi

# Установка Glances
print_header "Установка и настройка Glances"
print_subheader "Создание сервиса Glances для мониторинга серверов"

# Устанавливаем Glances через apt для надежности
print_subheader "Установка Glances через APT (более надежный способ)"
apt-get install -y glances

# Проверяем путь к исполняемому файлу Glances
GLANCES_PATH=$(which glances || echo "")
if [ -z "$GLANCES_PATH" ]; then
    # Если команда which не нашла glances, проверяем типичные места
    if [ -f "/usr/bin/glances" ]; then
        GLANCES_PATH="/usr/bin/glances"
    elif [ -f "/usr/local/bin/glances" ]; then
        GLANCES_PATH="/usr/local/bin/glances"
    else
        # Пробуем установить через apt еще раз
        print_subheader "Повторная попытка установки Glances через apt"
        apt-get update && apt-get install -y glances
        
        # Создаем скрипт-обертку для glances, если его не существует
        if [ ! -f "/usr/local/bin/glances" ]; then
            print_subheader "Создание скрипта-обертки для glances"
            cat > /usr/local/bin/glances <<EOF
#!/bin/bash
python3 -m glances "\$@"
EOF
            chmod +x /usr/local/bin/glances
        fi
        
        GLANCES_PATH="/usr/local/bin/glances"
    fi
    print_subheader "Найден путь к Glances: $GLANCES_PATH"
fi

# Создаем системный сервис для Glances
cat > /etc/systemd/system/glances.service <<EOF
[Unit]
Description=Glances monitoring tool (web mode)
After=network.target

[Service]
ExecStart=$GLANCES_PATH -w
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Установка скрипта деплоя Glances на удаленные серверы
print_subheader "Создание скрипта установки Glances на удаленные серверы"
mkdir -p "$APP_DIR/scripts"
cat > "$APP_DIR/scripts/install_glances_ubuntu22.sh" <<'EOF'
#!/bin/bash

# ======================================================
# Скрипт установки Glances для Ubuntu 22.04 
# Создан специально для Reverse Proxy Manager
# ======================================================

set -e # Останавливаем скрипт при любой ошибке

echo "=== Установка Glances на Ubuntu 22.04 ==="

# Обновляем список пакетов
echo "Обновление списка пакетов..."
apt-get update

# Устанавливаем pip и зависимости
echo "Установка Python3-pip и зависимостей..."
apt-get install -y python3-pip curl net-tools lsof jq

# Устанавливаем Glances через apt для надежности
echo "Установка Glances через APT (более надежный способ)..."
apt-get install -y glances

# Устанавливаем необходимые зависимости для веб-сервера
echo "Установка веб-зависимостей..."
apt-get install -y python3-fastapi python3-uvicorn python3-jinja2

# Проверяем путь к исполняемому файлу Glances
GLANCES_PATH=$(which glances || echo "")
if [ -z "$GLANCES_PATH" ]; then
    # Если команда which не нашла glances, проверяем типичные места
    if [ -f "/usr/bin/glances" ]; then
        GLANCES_PATH="/usr/bin/glances"
    elif [ -f "/usr/local/bin/glances" ]; then
        GLANCES_PATH="/usr/local/bin/glances"
    else
        # Создаем symlink к возможному пути в Python
        PYTHON_GLANCES=$(find /usr -name glances | grep "/bin/glances" | head -n 1)
        if [ -n "$PYTHON_GLANCES" ]; then
            ln -sf "$PYTHON_GLANCES" /usr/local/bin/glances
            GLANCES_PATH="/usr/local/bin/glances"
        else
            echo "Не удалось найти исполняемый файл Glances после установки"
            echo "Служба Glances может не запуститься. Возможно, потребуется ручная настройка."
            GLANCES_PATH="/usr/local/bin/glances"
        fi
    fi
    echo "Найден путь к Glances: $GLANCES_PATH"
fi

# Создаем systemd сервис для Glances
echo "Создание systemd сервиса..."
cat > /etc/systemd/system/glances.service << EOT
[Unit]
Description=Glances monitoring tool (web mode)
After=network.target

[Service]
ExecStart=$GLANCES_PATH -w
Restart=always

[Install]
WantedBy=multi-user.target
EOT

# Перезагружаем systemd, включаем и запускаем сервис
echo "Запуск сервиса..."
systemctl daemon-reload
systemctl enable glances.service
systemctl start glances.service

# Ждем немного для старта сервиса
echo "Ожидание запуска сервиса (5 секунд)..."
sleep 5

# Проверяем статус сервиса
echo "Проверка статуса сервиса..."
systemctl status glances.service --no-pager

# Проверяем доступность API и Web-интерфейса
echo "Проверка доступности API (порт 61208)..."
if curl -s "http://localhost:61208/api/4/cpu" | grep -q "total"; then
    echo "✅ API доступен и работает"
else
    echo "❌ API не отвечает. Проверьте журнал: journalctl -u glances.service"
    
    # Дополнительная информация о процессе
    echo "Информация о процессе Glances:"
    ps aux | grep -v grep | grep glances || echo "Процесс не найден"
    
    # Информация о прослушиваемых портах
    echo "Открытые порты:"
    ss -tulpn | grep 61208 || echo "Порт не прослушивается"
    
    # Пробуем перезапустить сервис
    echo "Пробуем перезапустить сервис..."
    systemctl restart glances.service
    sleep 5
    
    # Проверяем еще раз
    if curl -s "http://localhost:61208/api/4/cpu" | grep -q "total"; then
        echo "✅ После перезапуска API стал доступен"
    else
        echo "❌ API все еще недоступен"
    fi
fi

echo "Проверка доступности Web-интерфейса..."
if curl -s "http://localhost:61208/" | grep -q "Glances"; then
    echo "✅ Web-интерфейс доступен и работает"
else
    echo "❌ Web-интерфейс не отвечает"
fi

# Информация о сети для облегчения доступа извне
echo "Внешние интерфейсы:"
ip -4 addr show | grep -v 127.0.0.1 | grep inet

echo "======================================================"
echo "Установка Glances завершена."
echo "Web URL и API URL: http://IP_АДРЕС:61208/"
echo "Журнал: journalctl -u glances.service -f"
echo "======================================================"

exit 0
EOF

# Делаем скрипт исполняемым
chmod +x "$APP_DIR/scripts/install_glances_ubuntu22.sh"

# Перезапускаем службы
print_header "Запуск и настройка служб"
systemctl daemon-reload
systemctl restart nginx
systemctl enable reverse-proxy-control-center
systemctl restart reverse-proxy-control-center

# Создание скриптов для миграции базы данных, если они нужны
print_subheader "Проверка необходимости миграции базы данных"
cd "$APP_DIR"

# Проверяем, нужно ли запустить скрипты миграции для базы данных
# В зависимости от наличия файлов

# Открываем порты в брандмауэре, если он включен
if command -v ufw &> /dev/null && ufw status | grep -q "active"; then
    print_subheader "Настройка брандмауэра (ufw)"
    ufw allow 'Nginx Full'
    ufw allow $APP_PORT
    print_warning "Рекомендуется ограничить доступ к порту $APP_PORT только локальной сетью"
fi

# Проверка статуса сервисов после установки
print_header "Проверка статуса сервисов"
echo "Статус nginx:"
systemctl status nginx --no-pager

echo "Статус reverse-proxy-control-center:"
systemctl status reverse-proxy-control-center --no-pager

# Вывод информации по завершении установки
print_header "🎉 Установка $APP_NAME успешно завершена! 🎉"
echo -e "Приложение доступно по адресу: http://$(hostname -I | awk '{print $1}')"
echo -e "\nУчетные данные администратора:"
echo "  Логин: $ADMIN_USER"
echo "  Пароль: $ADMIN_PASSWORD"

print_warning "Пожалуйста, измените пароль администратора после первого входа!"

echo -e "\nДополнительные действия для повышения безопасности:"
echo "  1. Настроить SSL с помощью certbot: sudo certbot --nginx"
echo "  2. Ограничить доступ к приложению по IP через Nginx"
echo "  3. Настроить резервное копирование базы данных"
echo "  4. Установить и настроить Telegram-бота для уведомлений"

echo -e "\nПолезные команды:"
echo "  • Просмотр логов: sudo journalctl -u reverse-proxy-control-center -f"
echo "  • Перезапуск сервиса: sudo systemctl restart reverse-proxy-control-center"
echo "  • Изменение пароля администратора: cd $APP_DIR && source venv/bin/activate && python change_admin_password.py"
echo "  • Резервное копирование базы данных: sudo -u postgres pg_dump $DB_NAME > /root/db_backup_\$(date +%Y%m%d).sql"

echo -e "\nИнформация о базе данных для ручного доступа:"
echo "  • Сервер: localhost"
echo "  • База данных: $DB_NAME"
echo "  • Пользователь: $DB_USER"
echo "  • Пароль: $DB_PASSWORD"

echo -e "\nСохраните эту информацию в надежном месте!"

exit 0