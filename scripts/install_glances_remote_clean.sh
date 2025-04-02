#!/bin/bash

# Скрипт установки Glances на удаленном сервере
# Использование: ./install_glances_remote_clean.sh <ip-адрес> <пользователь> <ssh-ключ>

set -e

# Проверяем аргументы
if [ $# -lt 3 ]; then
    echo "Использование: $0 <ip-адрес> <пользователь> <ssh-ключ>"
    exit 1
fi

SERVER_IP=$1
SSH_USER=$2
SSH_KEY=$3

echo "Установка Glances на сервере $SERVER_IP..."

# Устанавливаем Glances на удаленном сервере
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$SERVER_IP" << 'EOF'
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev
pip3 install wheel
pip3 install "glances<=5.0" bottle

# Создаем сервис systemd для Glances
sudo tee /etc/systemd/system/glances.service > /dev/null << 'EOL'
[Unit]
Description=Glances
After=network.target

[Service]
ExecStart=/usr/local/bin/glances -w -t 5 --disable-plugin sensors --disable-plugin smart --disable-webui
Restart=on-abort
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOL

# Перезагружаем конфигурацию systemd
sudo systemctl daemon-reload

# Включаем и запускаем сервис Glances
sudo systemctl enable glances
sudo systemctl start glances

# Проверяем статус сервиса
sudo systemctl status glances

echo "Glances установлен и запущен на порту 61208"
EOF

echo "Установка Glances завершена на сервере $SERVER_IP"
echo "Для проверки доступности API выполните: curl http://$SERVER_IP:61208/api/4/all"