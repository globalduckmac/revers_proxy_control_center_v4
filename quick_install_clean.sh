#!/bin/bash

# Скрипт быстрой установки Reverse Proxy Control Center v4
# Автоматизирует процесс установки и настройки системы

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Начинаем установку Reverse Proxy Control Center v4...${NC}"

# Функция для установки необходимых системных зависимостей
install_dependencies() {
    echo -e "${YELLOW}Установка системных зависимостей...${NC}"
    apt-get update
    apt-get install -y python3 python3-pip python3-venv nginx postgresql postgresql-contrib libpq-dev python3-dev build-essential
    echo -e "${GREEN}Системные зависимости установлены.${NC}"
}

# Функция для настройки базы данных PostgreSQL
setup_database() {
    echo -e "${YELLOW}Настройка базы данных PostgreSQL...${NC}"
    sudo -u postgres psql -c "CREATE DATABASE reverse_proxy_control_center;" || echo "База данных уже существует"
    sudo -u postgres psql -c "CREATE USER rpcc_user WITH PASSWORD 'rpcc_password';" || echo "Пользователь уже существует"
    sudo -u postgres psql -c "ALTER ROLE rpcc_user SET client_encoding TO 'utf8';"
    sudo -u postgres psql -c "ALTER ROLE rpcc_user SET default_transaction_isolation TO 'read committed';"
    sudo -u postgres psql -c "ALTER ROLE rpcc_user SET timezone TO 'UTC';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE reverse_proxy_control_center TO rpcc_user;"
    echo -e "${GREEN}База данных PostgreSQL настроена.${NC}"
}

# Функция для настройки виртуальной среды Python
setup_python_venv() {
    echo -e "${YELLOW}Настройка виртуальной среды Python...${NC}"
    python3 -m venv /opt/rpcc/venv
    source /opt/rpcc/venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements-app.txt
    echo -e "${GREEN}Виртуальная среда Python настроена.${NC}"
}

# Функция для настройки приложения
setup_application() {
    echo -e "${YELLOW}Настройка приложения...${NC}"
    mkdir -p /opt/rpcc
    cp -r * /opt/rpcc/
    cd /opt/rpcc
    
    # Настройка переменных окружения
    cat > /opt/rpcc/.env << EOL
DATABASE_URL=postgresql://rpcc_user:rpcc_password@localhost/reverse_proxy_control_center
SESSION_SECRET=$(openssl rand -hex 32)
FLASK_APP=main.py
FLASK_ENV=production
EOL

    # Инициализация базы данных
    source /opt/rpcc/venv/bin/activate
    export DATABASE_URL=postgresql://rpcc_user:rpcc_password@localhost/reverse_proxy_control_center
    export SESSION_SECRET=$(openssl rand -hex 32)
    python init_db.py
    
    echo -e "${GREEN}Приложение настроено.${NC}"
}

# Функция для создания администратора
create_admin_user() {
    echo -e "${YELLOW}Создание пользователя-администратора...${NC}"
    source /opt/rpcc/venv/bin/activate
    cd /opt/rpcc
    export DATABASE_URL=postgresql://rpcc_user:rpcc_password@localhost/reverse_proxy_control_center
    export SESSION_SECRET=$(openssl rand -hex 32)
    python create_admin.py
    echo -e "${GREEN}Пользователь-администратор создан.${NC}"
}

# Функция для настройки службы systemd
setup_systemd_service() {
    echo -e "${YELLOW}Настройка службы systemd...${NC}"
    cat > /etc/systemd/system/reverse-proxy-control-center.service << EOL
[Unit]
Description=Reverse Proxy Control Center
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/rpcc
Environment="PATH=/opt/rpcc/venv/bin"
EnvironmentFile=/opt/rpcc/.env
ExecStart=/opt/rpcc/venv/bin/gunicorn --workers 2 --bind 0.0.0.0:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
EOL

    systemctl daemon-reload
    systemctl enable reverse-proxy-control-center
    systemctl start reverse-proxy-control-center
    echo -e "${GREEN}Служба systemd настроена.${NC}"
}

# Функция для настройки Nginx
setup_nginx() {
    echo -e "${YELLOW}Настройка Nginx...${NC}"
    cat > /etc/nginx/sites-available/reverse-proxy-control-center << EOL
server {
    listen 80;
    server_name _;

    location / {
        include proxy_params;
        proxy_pass http://localhost:5000;
    }
}
EOL

    # Удаляем дефолтную конфигурацию и включаем нашу
    rm -f /etc/nginx/sites-enabled/default
    ln -sf /etc/nginx/sites-available/reverse-proxy-control-center /etc/nginx/sites-enabled/
    systemctl restart nginx
    echo -e "${GREEN}Nginx настроен.${NC}"
}

# Функция для установки Glances
install_glances() {
    echo -e "${YELLOW}Установка Glances...${NC}"
    source /opt/rpcc/venv/bin/activate
    pip install "glances<=5.0"
    
    # Настройка Glances как службы systemd
    cat > /etc/systemd/system/glances.service << EOL
[Unit]
Description=Glances
After=network.target

[Service]
ExecStart=/opt/rpcc/venv/bin/glances -w -t 5 --disable-plugin sensors --disable-plugin smart --disable-webui
Restart=on-abort
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOL

    systemctl daemon-reload
    systemctl enable glances
    systemctl start glances
    echo -e "${GREEN}Glances установлен и настроен.${NC}"
}

# Основной процесс установки
main() {
    echo -e "${BLUE}Запуск процесса установки...${NC}"
    
    # Создаем директорию для приложения
    mkdir -p /opt/rpcc
    
    # Выполняем каждую функцию установки
    install_dependencies
    setup_database
    setup_python_venv
    setup_application
    create_admin_user
    setup_systemd_service
    setup_nginx
    install_glances
    
    # Финальное сообщение
    IP_ADDRESS=$(hostname -I | awk '{print $1}')
    echo -e "${GREEN}===================================================${NC}"
    echo -e "${GREEN}Reverse Proxy Control Center v4 успешно установлен!${NC}"
    echo -e "${GREEN}Доступ к панели управления: http://$IP_ADDRESS/${NC}"
    echo -e "${GREEN}Логин: admin@example.com${NC}"
    echo -e "${GREEN}Пароль: admin (смените его после первого входа)${NC}"
    echo -e "${GREEN}===================================================${NC}"
}

# Запуск установки
main