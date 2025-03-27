#!/bin/bash

# Скрипт для установки Glances на удаленном сервере
# Использование: ./install_glances.sh <api_port> <web_port>

# Параметры
API_PORT=${1:-61208}
WEB_PORT=${2:-61209}

# Установка необходимых пакетов
echo "Установка необходимых пакетов..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-dev build-essential supervisor python3-psutil

# Создаем виртуальное окружение для Glances
echo "Создание окружения для Glances..."
pip3 install -U pip
pip3 install glances[web]

# Создаем файл конфигурации Glances
echo "Настройка конфигурации Glances..."
mkdir -p /etc/glances
cat > /etc/glances/glances.conf << EOF
[global]
# Показывать IP-адреса в статистике сети
network_ip_public_global_only = False

[outputs]
# Отрисовка в консоли
curse_theme = dark
disable_cursor = True

# Включить веб-сервер
[web]
host = 0.0.0.0
port = ${WEB_PORT}
open_browser = False
allow_all_origins = True

# Включить REST API
[api]
host = 0.0.0.0
port = ${API_PORT}
allow_all_origins = True

# Настройка мониторинга дисков
[diskio]
hide=loop.*,/dev/loop.*

# Настройка мониторинга сети
[network]
hide=lo

# Настройка процессов
[processlist]
min_user_filter = root, 
max_processes = 50
tree = False

# Настройка просмотра файловых систем
[fs]
hide=/boot.*,/snap.*,/dev/loop.*
EOF

# Создаем systemd сервис для Glances
echo "Создание systemd-сервиса..."
cat > /etc/systemd/system/glances.service << EOF
[Unit]
Description=Glances server
After=network.target

[Service]
ExecStart=/usr/local/bin/glances -w -s --disable-plugin docker --config /etc/glances/glances.conf
Restart=on-failure
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

# Создаем конфигурацию для supervisor (альтернатива systemd)
echo "Настройка supervisor..."
cat > /etc/supervisor/conf.d/glances.conf << EOF
[program:glances]
command=/usr/local/bin/glances -w -s --disable-plugin docker --config /etc/glances/glances.conf
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/glances.log
EOF

# Включаем и запускаем сервисы
echo "Запуск сервисов..."
systemctl daemon-reload
systemctl enable glances.service
systemctl start glances.service

# Перезапускаем supervisor для применения изменений
supervisorctl reread
supervisorctl update
supervisorctl restart glances

# Проверяем, что Glances запущен
echo "Проверка статуса Glances..."
systemctl status glances.service
curl -s http://localhost:${API_PORT}/api/3/cpu | grep -q "total" && echo "API доступен на порту ${API_PORT}" || echo "Ошибка: API недоступен"
curl -s http://localhost:${WEB_PORT} | grep -q "Glances" && echo "Веб-интерфейс доступен на порту ${WEB_PORT}" || echo "Ошибка: веб-интерфейс недоступен"

echo "Установка Glances завершена."
echo "API URL: http://localhost:${API_PORT}"
echo "Web URL: http://localhost:${WEB_PORT}"

exit 0