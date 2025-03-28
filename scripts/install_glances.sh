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
pip3 install -U pip setuptools wheel
# Устанавливаем совместимую версию Glances
pip3 install "glances[web]<=5.0"

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
ExecStart=/usr/local/bin/glances -w -s --disable-plugin docker --bind 0.0.0.0 --port ${API_PORT} --webserver-port ${WEB_PORT}
Restart=always
RestartSec=10
User=root
Group=root
Environment="PYTHONUNBUFFERED=1"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Создаем конфигурацию для supervisor (альтернатива systemd)
echo "Настройка supervisor..."
cat > /etc/supervisor/conf.d/glances.conf << EOF
[program:glances]
command=/usr/local/bin/glances -w -s --disable-plugin docker --bind 0.0.0.0 --port ${API_PORT} --webserver-port ${WEB_PORT}
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/glances.log
directory=/tmp
startretries=10
startsecs=10
stopwaitsecs=10
stopasgroup=true
killing_timeout=30
environment=PYTHONUNBUFFERED="1"
EOF

# Включаем и запускаем сервисы
echo "Запуск сервисов..."
systemctl daemon-reload
systemctl enable glances.service
systemctl start glances.service

# Дополнительная проверка и перезапуск, если сервис не запустился
if ! systemctl is-active --quiet glances.service; then
    echo "Сервис glances не запустился, пробуем перезапустить..."
    systemctl restart glances.service
    sleep 5
fi

# Пробуем альтернативный способ с supervisor
echo "Настройка supervisor (альтернативный метод)..."
supervisorctl reread
supervisorctl update
supervisorctl restart glances

# Проверяем запущен ли хотя бы один из способов
if ! (systemctl is-active --quiet glances.service || supervisorctl status glances | grep -q RUNNING); then
    echo "Запускаем Glances напрямую через nohup..."
    nohup /usr/local/bin/glances -w -s --disable-plugin docker --bind 0.0.0.0 --port ${API_PORT} --webserver-port ${WEB_PORT} > /var/log/glances_nohup.log 2>&1 &
    sleep 5
fi

# Проверяем, что Glances запущен
echo "Проверка статуса Glances..."
systemctl status glances.service || echo "Systemd service check failed, trying supervisor..."
supervisorctl status glances || echo "Supervisor check failed, checking process..."
ps aux | grep -v grep | grep "glances -w" || echo "Process check failed"

# Проверяем доступность API
echo "Проверка доступности API..."
for i in {1..5}; do
    echo "Попытка $i из 5..."
    if curl -s http://localhost:${API_PORT}/api/3/cpu | grep -q "total"; then
        echo "API доступен на порту ${API_PORT}"
        API_ACCESSIBLE=true
        break
    else
        echo "API недоступен на порту ${API_PORT}, подождем 2 секунды..."
        sleep 2
    fi
done

if [ -z "$API_ACCESSIBLE" ]; then
    echo "Пробуем альтернативные способы запуска Glances..."
    
    # Пробуем запустить через nohup напрямую (с публичным доступом)
    echo "Запуск через nohup с публичным доступом..."
    pkill -f "glances -w" || true
    nohup /usr/local/bin/glances -w -s --disable-plugin docker --bind 0.0.0.0 --port ${API_PORT} --webserver-port ${WEB_PORT} > /var/log/glances_nohup.log 2>&1 &
    
    echo "Ждем 5 секунд..."
    sleep 5
    
    # Проверяем еще раз
    if curl -s http://localhost:${API_PORT}/api/3/cpu | grep -q "total"; then
        echo "API доступен на порту ${API_PORT} после прямого запуска"
    else
        # Проверяем от имени 0.0.0.0 и через внешний IP
        PUBLIC_IP=$(curl -s http://ifconfig.me)
        
        if curl -s http://0.0.0.0:${API_PORT}/api/3/cpu | grep -q "total"; then
            echo "API доступен через 0.0.0.0:${API_PORT}"
        elif curl -s http://${PUBLIC_IP}:${API_PORT}/api/3/cpu | grep -q "total"; then
            echo "API доступен через ${PUBLIC_IP}:${API_PORT}"
        else
            echo "ВНИМАНИЕ: API все еще недоступен. Проверяем порты..."
            netstat -tulpn | grep ${API_PORT} || ss -tulpn | grep ${API_PORT}
            echo "Ошибка: API недоступен после всех попыток"
        fi
    fi
fi

# Проверяем веб-интерфейс
if curl -s http://localhost:${WEB_PORT} | grep -q "Glances"; then
    echo "Веб-интерфейс доступен на порту ${WEB_PORT}"
else
    echo "Веб-интерфейс недоступен на порту ${WEB_PORT}"
fi

# Добавляем запуск Glances при старте системы, используя несколько методов
echo "Настройка автозапуска при старте системы..."
echo "@reboot root /usr/local/bin/glances -w -s --disable-plugin docker --bind 0.0.0.0 --port ${API_PORT} --webserver-port ${WEB_PORT} > /var/log/glances_boot.log 2>&1" > /etc/cron.d/glances-autostart
chmod 644 /etc/cron.d/glances-autostart

echo "Установка Glances завершена. Если Glances не работает, перезагрузите сервер и проверьте еще раз."
echo "API URL: http://localhost:${API_PORT}"
echo "Web URL: http://localhost:${WEB_PORT}"

exit 0