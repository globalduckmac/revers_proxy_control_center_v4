#!/bin/bash

# Скрипт для установки Glances на внешний сервер
# Использование: ./install_glances_remote.sh <username> <hostname/ip> [ssh_port]

# Проверка наличия всех аргументов
if [ "$#" -lt 2 ]; then
    echo "Использование: $0 <username> <hostname/ip> [ssh_port]"
    exit 1
fi

USERNAME="$1"
HOSTNAME="$2"
SSH_PORT="${3:-22}"  # По умолчанию порт SSH - 22

echo "Установка Glances на сервер $HOSTNAME (пользователь: $USERNAME, SSH порт: $SSH_PORT)"

# Функция для SSH подключения и выполнения команд
run_ssh_command() {
    ssh -p "$SSH_PORT" "$USERNAME@$HOSTNAME" "$1"
}

# 1. Обновление репозиториев
echo "1. Обновление репозиториев..."
run_ssh_command "sudo apt update" || {
    echo "Ошибка при обновлении репозиториев"
    exit 1
}

# 2. Установка Python и pip
echo "2. Установка Python и pip..."
run_ssh_command "sudo apt install -y python3-pip" || {
    echo "Ошибка при установке python3-pip"
    exit 1
}

# 3. Установка Glances через pip
echo "3. Установка Glances..."
run_ssh_command "sudo pip3 install --upgrade glances" || {
    echo "Ошибка при установке Glances"
    exit 1
}

# 4. Установка необходимых зависимостей для веб-интерфейса
echo "4. Установка зависимостей для веб-интерфейса..."
run_ssh_command "sudo pip3 install fastapi uvicorn jinja2" || {
    echo "Ошибка при установке зависимостей"
    exit 1
}

# 5-6. Создание файла службы systemd
echo "5. Создание файла службы systemd..."
SERVICE_FILE=$(cat <<EOF
[Unit]
Description=Glances monitoring tool (web mode)
After=network.target

[Service]
ExecStart=/usr/local/bin/glances -w
Restart=always

[Install]
WantedBy=multi-user.target
EOF
)

# Отправка сервисного файла на удаленный сервер
echo "$SERVICE_FILE" | ssh -p "$SSH_PORT" "$USERNAME@$HOSTNAME" "cat > /tmp/glances.service"

# Установка сервиса в systemd
run_ssh_command "sudo mv /tmp/glances.service /etc/systemd/system/glances.service" || {
    echo "Ошибка при создании файла сервиса"
    exit 1
}

# 7. Перезагрузка systemd после создания нового файла службы
echo "7. Перезагрузка systemd..."
run_ssh_command "sudo systemctl daemon-reload" || {
    echo "Ошибка при перезагрузке systemd"
    exit 1
}

# 8. Включение автозапуска Glances
echo "8. Включение автозапуска Glances..."
run_ssh_command "sudo systemctl enable glances.service" || {
    echo "Ошибка при включении автозапуска"
    exit 1
}

# 9. Запуск службы Glances
echo "9. Запуск службы Glances..."
run_ssh_command "sudo systemctl start glances.service" || {
    echo "Ошибка при запуске службы"
    exit 1
}

# Проверка статуса службы
echo "Проверка статуса службы Glances..."
run_ssh_command "sudo systemctl status glances.service" || {
    echo "Ошибка при проверке статуса службы"
}

# Проверка доступности Glances через HTTP
echo "Проверка доступности Glances веб-интерфейса..."
sleep 5  # Даем Glances время на запуск
run_ssh_command "curl -s http://localhost:61208/api/4/all | grep -q 'cpu' && echo 'API доступен на порту 61208' || echo 'API недоступен'"

echo ""
echo "Установка завершена!"
echo "Glances должен быть доступен по адресу http://$HOSTNAME:61208"
echo "API доступен по адресу http://$HOSTNAME:61208/api/4/all"
echo "Если у вас возникли проблемы с доступом, убедитесь, что порт 61208 открыт в брандмауэре:"
echo "sudo ufw allow 61208/tcp   # для Ubuntu/Debian с UFW"
echo "или"
echo "sudo firewall-cmd --permanent --add-port=61208/tcp && sudo firewall-cmd --reload   # для CentOS/RHEL/Fedora с firewalld"
echo ""