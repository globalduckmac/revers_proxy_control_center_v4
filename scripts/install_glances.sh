#!/bin/bash

# Скрипт для установки Glances на удаленном сервере
# Использование: ./install_glances.sh

echo "Установка Glances..."

# 1. Обновление репозиториев
echo "1. Обновление репозиториев..."
sudo apt update

# 2. Установка Python и pip
echo "2. Установка Python и pip..."
sudo apt install -y python3-pip

# 3. Установка Glances через pip
echo "3. Установка Glances..."
sudo pip3 install --upgrade glances

# 4. Установка необходимых зависимостей для веб-интерфейса
echo "4. Установка зависимостей для веб-интерфейса..."
sudo pip3 install fastapi uvicorn jinja2

# 5-6. Создание файла службы systemd
echo "5. Создание файла службы systemd..."
cat > /tmp/glances.service << EOF
[Unit]
Description=Glances monitoring tool (web mode)
After=network.target

[Service]
ExecStart=/usr/local/bin/glances -w
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/glances.service /etc/systemd/system/glances.service

# 7. Перезагрузка systemd после создания нового файла службы
echo "7. Перезагрузка systemd..."
sudo systemctl daemon-reload

# 8. Включение автозапуска Glances
echo "8. Включение автозапуска Glances..."
sudo systemctl enable glances.service

# 9. Запуск службы Glances
echo "9. Запуск службы Glances..."
sudo systemctl start glances.service

# Проверка статуса службы
echo "Проверка статуса службы Glances..."
sudo systemctl status glances.service

# Проверка доступности API
echo "Проверка доступности API..."
for i in {1..5}; do
    echo "Попытка $i из 5..."
    if curl -s http://localhost:61208/api/4/all | grep -q "cpu"; then
        echo "API доступен на порту 61208"
        API_ACCESSIBLE=true
        break
    else
        echo "API недоступен на порту 61208, подождем 2 секунды..."
        sleep 2
    fi
done

if [ -z "$API_ACCESSIBLE" ]; then
    echo "ВНИМАНИЕ: API недоступен после всех попыток"
    echo "Проверяем, запущен ли сервис..."
    ps aux | grep -v grep | grep "glances -w"
    echo "Проверяем открытые порты..."
    ss -tulpn | grep 61208 || netstat -tulpn | grep 61208
fi

echo "Установка Glances завершена."
echo "Веб-интерфейс: http://$(hostname -I | awk '{print $1}'):61208"
echo "API: http://$(hostname -I | awk '{print $1}'):61208/api/4/all"

exit 0