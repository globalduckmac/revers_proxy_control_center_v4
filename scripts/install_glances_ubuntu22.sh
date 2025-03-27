#!/bin/bash

# ======================================================
# Скрипт установки Glances для Ubuntu 22.04 
# Создан специально для Reverse Proxy Manager
# ======================================================

set -e # Останавливаем скрипт при любой ошибке

# Получаем порты из параметров или используем значения по умолчанию
API_PORT=${1:-61208}
WEB_PORT=${2:-61209}

echo "=== Установка Glances на Ubuntu 22.04 ==="
echo "=== API порт: $API_PORT, Веб-порт: $WEB_PORT ==="

# Обновляем список пакетов
echo "Обновление списка пакетов..."
apt-get update

# Устанавливаем необходимые зависимости
echo "Установка необходимых пакетов..."
apt-get install -y python3-pip python3-dev python3-venv curl wget net-tools lsof jq

# Создаем виртуальное окружение для Glances
echo "Создание виртуального окружения для Glances..."
python3 -m venv /opt/glances_venv

# Активируем виртуальное окружение и устанавливаем Glances
echo "Установка Glances в виртуальное окружение..."
/opt/glances_venv/bin/pip install --upgrade pip
/opt/glances_venv/bin/pip install glances[web]

# Создаем директорию для конфигурации
echo "Создание директории конфигурации..."
mkdir -p /etc/glances

# Создаем базовую конфигурацию Glances
echo "Создание конфигурационного файла..."
cat > /etc/glances/glances.conf << 'EOF'
[global]
# Отключаем проверку обновлений
check_update=False

[quicklook]
# CPU, MEM и LOAD отображаются в пользовательском интерфейсе
cpu_careful=70
cpu_warning=80
cpu_critical=90
mem_careful=70
mem_warning=80
mem_critical=90

[stats]
# Включаем/выключаем статистики
disable_docker=True
disable_sensors=False
disable_wifi=False
wifi_careful=50
wifi_warning=70
wifi_critical=85

[ports]
# Укажем порты, по которым будет доступен Glances
port_listen_all_interfaces=True

[webserver]
# Чтобы веб-сервер слушал на всех интерфейсах
host=0.0.0.0
port=WEB_PORT

[restful]
host=0.0.0.0
port=API_PORT
EOF

# Подставляем реальные номера портов в конфигурацию
sed -i "s/WEB_PORT/$WEB_PORT/g" /etc/glances/glances.conf
sed -i "s/API_PORT/$API_PORT/g" /etc/glances/glances.conf

# Проверяем порты на занятость
echo "Проверка доступности портов..."
if lsof -i:$API_PORT > /dev/null 2>&1; then
    echo "ПРЕДУПРЕЖДЕНИЕ: Порт $API_PORT уже используется. Glances может не запуститься."
    lsof -i:$API_PORT
fi

if lsof -i:$WEB_PORT > /dev/null 2>&1; then
    echo "ПРЕДУПРЕЖДЕНИЕ: Порт $WEB_PORT уже используется. Glances может не запуститься."
    lsof -i:$WEB_PORT
fi

# Создаем systemd сервис для Glances
echo "Создание systemd сервиса..."
cat > /etc/systemd/system/glances.service << EOF
[Unit]
Description=Glances Server
After=network.target

[Service]
ExecStart=/opt/glances_venv/bin/python -m glances -w -s --disable-plugin docker --config /etc/glances/glances.conf
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=glances
User=root
Group=root

# Важные параметры для надежной работы
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/tmp
KillSignal=SIGTERM
TimeoutStopSec=30
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
EOF

# Перезагружаем systemd, включаем и запускаем сервис
echo "Запуск сервиса..."
systemctl daemon-reload
systemctl enable glances.service
systemctl start glances.service

# Ждем немного для старта сервиса
echo "Ожидание запуска сервиса (10 секунд)..."
sleep 10

# Проверяем статус сервиса
echo "Проверка статуса сервиса..."
systemctl status glances.service --no-pager

# Проверяем доступность API и Web-интерфейса
echo "Проверка доступности API (порт $API_PORT)..."
if curl -s "http://localhost:$API_PORT/api/3/cpu" | grep -q "total"; then
    echo "✅ API доступен и работает"
else
    echo "❌ API не отвечает. Проверьте журнал: journalctl -u glances.service"
    
    # Дополнительная информация о процессе
    echo "Информация о процессе Glances:"
    ps aux | grep -v grep | grep glances || echo "Процесс не найден"
    
    # Информация о прослушиваемых портах
    echo "Открытые порты:"
    ss -tulpn | grep -E "$API_PORT|$WEB_PORT" || echo "Порты не прослушиваются"
    
    # Пробуем перезапустить сервис
    echo "Пробуем перезапустить сервис..."
    systemctl restart glances.service
    sleep 5
    
    # Проверяем еще раз
    if curl -s "http://localhost:$API_PORT/api/3/cpu" | grep -q "total"; then
        echo "✅ После перезапуска API стал доступен"
    else
        echo "❌ API все еще недоступен"
    fi
fi

echo "Проверка доступности Web-интерфейса (порт $WEB_PORT)..."
if curl -s "http://localhost:$WEB_PORT/" | grep -q "Glances"; then
    echo "✅ Web-интерфейс доступен и работает"
else
    echo "❌ Web-интерфейс не отвечает"
fi

# Информация о сети для облегчения доступа извне
echo "Внешние интерфейсы:"
ip -4 addr show | grep -v 127.0.0.1 | grep inet

echo "======================================================"
echo "Установка Glances завершена."
echo "API URL: http://IP_АДРЕС:$API_PORT/api/3"
echo "Web URL: http://IP_АДРЕС:$WEB_PORT"
echo "Журнал: journalctl -u glances.service -f"
echo "======================================================"

exit 0