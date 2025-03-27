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

# Устанавливаем Glances из системных репозиториев
echo "Установка Glances..."
apt-get install -y glances curl net-tools lsof jq

# Создаем systemd сервис для Glances
echo "Создание systemd сервиса..."
cat > /etc/systemd/system/glances.service << EOF
[Unit]
Description=Glances monitoring tool (web mode)
After=network.target

[Service]
ExecStart=/usr/bin/glances -w
Restart=always

[Install]
WantedBy=multi-user.target
EOF

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