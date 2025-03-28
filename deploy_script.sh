#!/bin/bash

# Скрипт установки Reverse Proxy Control Center v3
# Обновленная версия со всеми исправлениями

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Функции для вывода
print_header() {
    echo -e "\n${GREEN}=== $1 ===${NC}"
}

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка root-прав
if [ "$(id -u)" != "0" ]; then
   print_error "Этот скрипт должен быть запущен с правами root (sudo)"
   exit 1
fi

# Начальные параметры
APP_DIR="/opt/reverse_proxy_control_center"
SERVER_IP=$(hostname -I | awk '{print $1}')
SESSION_SECRET=$(openssl rand -hex 32)
ADMIN_PASSWORD=$(openssl rand -base64 8 | tr -dc 'a-zA-Z0-9')
DB_PASSWORD=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9')

print_header "Reverse Proxy Control Center v3 - Установка"
print_info "Сервер: $SERVER_IP"
print_info "Директория установки: $APP_DIR"

# Установка зависимостей
print_header "Установка зависимостей"
apt update
apt install -y git python3 python3-pip python3-venv nginx postgresql curl apt-transport-https ca-certificates

# Создание директории приложения
print_header "Подготовка файловой системы"
mkdir -p "$APP_DIR"
mkdir -p /var/log/reverse_proxy_control_center

# Клонирование репозитория
print_header "Клонирование репозитория"
if [ -d "$APP_DIR/.git" ]; then
    print_info "Репозиторий уже существует. Обновляем..."
    cd "$APP_DIR"
    git config --global --add safe.directory "$APP_DIR"
    git reset --hard HEAD
    git pull
else
    print_info "Клонируем репозиторий..."
    rm -rf "$APP_DIR"/*
    git clone https://github.com/globalduckmac/revers_proxy_control_center_v3.git "$APP_DIR"
    git config --global --add safe.directory "$APP_DIR"
fi

# Настройка PostgreSQL
print_header "Настройка PostgreSQL"
print_info "Проверка статуса PostgreSQL..."
if ! systemctl is-active --quiet postgresql; then
    print_info "Запускаем PostgreSQL..."
    systemctl start postgresql
    systemctl enable postgresql
fi

print_info "Настройка базы данных..."
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='rpcc'" | grep -q 1; then
    print_info "Пользователь базы данных 'rpcc' уже существует"
else
    print_info "Создание пользователя базы данных 'rpcc'..."
    sudo -u postgres psql -c "CREATE USER rpcc WITH PASSWORD '$DB_PASSWORD';"
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='rpcc'" | grep -q 1; then
    print_info "База данных 'rpcc' уже существует"
else
    print_info "Создание базы данных 'rpcc'..."
    sudo -u postgres psql -c "CREATE DATABASE rpcc OWNER rpcc;"
fi

# Настройка конфигурации
print_header "Обновление файла конфигурации"
if [ -f "$APP_DIR/config.py" ]; then
    # Обновляем строку подключения к базе данных на PostgreSQL
    sed -i "s|'mysql://root:password@localhost/reverse_proxy_manager'|'postgresql://rpcc:$DB_PASSWORD@localhost/rpcc'|g" "$APP_DIR/config.py"
    print_info "Файл config.py успешно обновлен для использования PostgreSQL"
else
    print_warning "Файл config.py не найден. Пропускаем обновление."
fi

# Настройка виртуального окружения Python
print_header "Настройка виртуального окружения Python"
cd "$APP_DIR"

if [ -d "$APP_DIR/venv" ]; then
    print_info "Виртуальное окружение уже существует. Обновляем..."
else
    print_info "Создание виртуального окружения..."
    python3 -m venv venv
fi

print_info "Установка зависимостей Python..."
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install flask flask-login flask-sqlalchemy flask-wtf gunicorn psycopg2-binary python-telegram-bot==13.15 pytz requests cryptography jinja2 werkzeug dnspython email-validator paramiko pymysql

# Установка прав доступа
print_header "Настройка прав доступа"
chown -R www-data:www-data "$APP_DIR"
chmod -R 755 "$APP_DIR"
chown -R www-data:www-data /var/log/reverse_proxy_control_center

# Исправление импортов если есть проблема с routes.domain vs routes.domains
print_header "Проверка и исправление импортов"
if [ -f "$APP_DIR/app.py" ]; then
    # Запускаем скрипт fix_imports.sh если он есть
    if [ -f "$APP_DIR/fix_imports.sh" ]; then
        print_info "Запускаем скрипт исправления импортов..."
        cd "$APP_DIR"
        bash fix_imports.sh
    else
        print_info "Исправляем импорты вручную..."
        if grep -q "routes\.domain" "$APP_DIR/app.py"; then
            print_info "Найдены ссылки на routes.domain, исправляем на routes.domains..."
            sed -i 's/import routes\.domain/import routes.domains/g' "$APP_DIR/app.py"
            sed -i 's/from routes\.domain import/from routes.domains import/g' "$APP_DIR/app.py" 
            sed -i 's/routes\.domain\./routes.domains./g' "$APP_DIR/app.py"
        fi
        
        if grep -q "routes\.server" "$APP_DIR/app.py"; then
            print_info "Найдены ссылки на routes.server, исправляем на routes.servers..."
            sed -i 's/import routes\.server/import routes.servers/g' "$APP_DIR/app.py"
            sed -i 's/from routes\.server import/from routes.servers import/g' "$APP_DIR/app.py"
            sed -i 's/routes\.server\./routes.servers./g' "$APP_DIR/app.py"
        fi
    fi
fi

# Настройка Nginx
print_header "Настройка Nginx"
cat > /etc/nginx/sites-available/reverse_proxy_control_center << EOF
server {
    listen 80;
    server_name $SERVER_IP;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Включение сайта Nginx
if [ -f /etc/nginx/sites-enabled/reverse_proxy_control_center ]; then
    print_info "Конфигурация Nginx уже включена"
else
    ln -s /etc/nginx/sites-available/reverse_proxy_control_center /etc/nginx/sites-enabled/
    print_info "Конфигурация Nginx успешно включена"
fi

# Проверка конфигурации Nginx
print_info "Проверка конфигурации Nginx..."
nginx -t
if [ $? -ne 0 ]; then
    print_error "Ошибка в конфигурации Nginx. Пожалуйста, проверьте и исправьте ошибки."
    exit 1
fi

# Настройка Glances для всех серверов
print_header "Создание скрипта установки Glances"

# Сначала создаем файл сервиса Glances напрямую
print_header "Создание systemd сервисного файла для Glances"
sudo tee /etc/systemd/system/glances.service > /dev/null << 'EOF'
[Unit]
Description=Glances monitoring tool (web mode)
After=network.target

[Service]
ExecStart=/usr/local/bin/glances -w
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Устанавливаем правильные разрешения
sudo chmod 644 /etc/systemd/system/glances.service

# Создаем упрощенный скрипт установки Glances без создания сервисного файла
sudo tee "$APP_DIR/install_glances.sh" > /dev/null << 'EOFGLANCES'
#!/bin/bash

# Скрипт для установки Glances на Ubuntu 22.04+ с поддержкой веб-интерфейса
# Запуск: sudo bash install_glances.sh

# Определение цветов для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Проверка, запущен ли скрипт от имени root
if [ "$(id -u)" != "0" ]; then
    echo -e "${RED}[ERROR]${NC} Этот скрипт должен быть запущен с правами root (sudo)."
    exit 1
fi

# Проверяем, установлен ли Python 3
if ! command -v python3 &>/dev/null; then
    echo -e "${GREEN}[INFO]${NC} Python3 не найден. Устанавливаем..."
    apt-get update
    apt-get install -y python3 python3-pip
else
    echo -e "${GREEN}[INFO]${NC} Python3 уже установлен: $(python3 --version)"
fi

# Устанавливаем pip и зависимости
echo -e "${GREEN}[INFO]${NC} Установка Python3-pip и зависимостей..."
apt-get install -y python3-pip curl net-tools lsof jq

# Устанавливаем Glances через pip в совместимой версии
echo -e "${GREEN}[INFO]${NC} Установка Glances через pip..."
pip3 install --upgrade pip setuptools wheel
pip3 install "glances[web]<=5.0"

# Устанавливаем необходимые зависимости для веб-сервера
echo -e "${GREEN}[INFO]${NC} Установка веб-зависимостей..."
pip3 install fastapi uvicorn jinja2

# Перезагружаем systemd, включаем и запускаем сервис
echo -e "${GREEN}[INFO]${NC} Запуск сервиса..."
systemctl daemon-reload
systemctl enable glances.service
systemctl restart glances.service

# Ждем немного для старта сервиса
echo -e "${GREEN}[INFO]${NC} Ожидание запуска сервиса (5 секунд)..."
sleep 5

# Проверяем статус сервиса
echo -e "${GREEN}[INFO]${NC} Проверка статуса сервиса..."
systemctl status glances.service --no-pager

# Проверяем доступность API и Web-интерфейса
echo -e "${GREEN}[INFO]${NC} Проверка доступности API (порт 61208)..."
if curl -s "http://localhost:61208/api/4/cpu" | grep -q "total"; then
    echo -e "${GREEN}[INFO]${NC} ✅ API доступен и работает"
else
    echo -e "${YELLOW}[WARN]${NC} ❌ API не отвечает. Проверьте журнал: journalctl -u glances.service"
    
    # Дополнительная информация о процессе
    echo -e "${GREEN}[INFO]${NC} Информация о процессе Glances:"
    ps aux | grep -v grep | grep glances || echo "Процесс не найден"
    
    # Информация о прослушиваемых портах
    echo -e "${GREEN}[INFO]${NC} Открытые порты:"
    ss -tulpn | grep 61208 || echo "Порт не прослушивается"
    
    # Пробуем перезапустить сервис
    echo -e "${GREEN}[INFO]${NC} Пробуем перезапустить сервис..."
    systemctl restart glances.service
    sleep 5
    
    # Проверяем еще раз
    if curl -s "http://localhost:61208/api/4/cpu" | grep -q "total"; then
        echo -e "${GREEN}[INFO]${NC} ✅ После перезапуска API стал доступен"
    else
        echo -e "${YELLOW}[WARN]${NC} ❌ API все еще недоступен"
    fi
fi

echo -e "${GREEN}[INFO]${NC} Проверка доступности Web-интерфейса..."
if curl -s "http://localhost:61208/" | grep -q "Glances"; then
    echo -e "${GREEN}[INFO]${NC} ✅ Web-интерфейс доступен и работает"
else
    echo -e "${YELLOW}[WARN]${NC} ❌ Web-интерфейс не отвечает"
fi

# Информация о сети для облегчения доступа извне
echo -e "${GREEN}[INFO]${NC} Внешние интерфейсы:"
ip -4 addr show | grep -v 127.0.0.1 | grep inet

echo -e "${GREEN}[INFO]${NC} ======================================================"
echo -e "${GREEN}[INFO]${NC} Установка Glances завершена."
echo -e "${GREEN}[INFO]${NC} Web URL и API URL: http://IP_АДРЕС:61208/"
echo -e "${GREEN}[INFO]${NC} Журнал: journalctl -u glances.service -f"
echo -e "${GREEN}[INFO]${NC} ======================================================"

exit 0
EOFGLANCES

# Делаем скрипт исполняемым
sudo chmod +x "$APP_DIR/install_glances.sh"

# Создание systemd сервиса
print_header "Создание systemd сервиса"
cat > /etc/systemd/system/reverse_proxy_control_center.service << EOF
[Unit]
Description=Reverse Proxy Control Center v3
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
Environment="DATABASE_URL=postgresql://rpcc:$DB_PASSWORD@localhost/rpcc"
Environment="SESSION_SECRET=$SESSION_SECRET"
ExecStartPre=/bin/sleep 2
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 --timeout 120 --access-logfile /var/log/reverse_proxy_control_center/access.log --error-logfile /var/log/reverse_proxy_control_center/error.log main:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Создание инструмента для диагностики
print_header "Создание инструмента диагностики"
sudo tee /usr/local/bin/rpcc-diagnose > /dev/null <<'EOF'
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
EOF

sudo chmod +x /usr/local/bin/rpcc-diagnose

# Включаем и запускаем сервис
print_header "Запуск сервиса"
sudo systemctl daemon-reload
sudo systemctl enable reverse_proxy_control_center
sudo systemctl restart reverse_proxy_control_center

# Перезагрузка Nginx
print_header "Перезапуск Nginx"
systemctl reload nginx

# Сохраняем учетные данные в файл
sudo tee /root/rpcc_credentials.txt > /dev/null <<EOF
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
EOF

sudo chmod 600 /root/rpcc_credentials.txt

# Создаем задачу cron для удаления файла с учетными данными через 24 часа
(sudo crontab -l 2>/dev/null; echo "$(date -d '24 hours' +'%M %H %d %m *') rm -f /root/rpcc_credentials.txt") | sudo crontab -

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
if curl -s http://localhost > /dev/null; then
    echo -e "\n${GREEN}[УСПЕХ]${NC} Веб-приложение доступно! Сервер успешно запущен."
else
    echo -e "\n${YELLOW}[ПРЕДУПРЕЖДЕНИЕ]${NC} Веб-приложение пока недоступно."
    echo "Запускаем диагностику..."
    sudo /usr/local/bin/rpcc-diagnose
    
    echo -e "\n${YELLOW}[СОВЕТ]${NC} Если веб-приложение недоступно, возможно, ему требуется больше времени для запуска."
    echo "Проверьте статус через несколько минут: systemctl status reverse_proxy_control_center"
fi