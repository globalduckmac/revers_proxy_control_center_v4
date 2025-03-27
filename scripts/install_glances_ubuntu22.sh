#!/bin/bash

# Скрипт установки Glances для Ubuntu 22.04
# Устанавливает Glances через apt и настраивает systemd-сервис
# для автоматического запуска API и веб-интерфейса на порту 61208

# Выход при любой ошибке
set -e

echo "Начало установки Glances на Ubuntu 22.04..."

# Проверка root прав
if [ "$EUID" -ne 0 ]; then
    if ! command -v sudo &>/dev/null; then
        echo "Ошибка: Необходимы права root для установки. Пожалуйста, запустите скрипт с sudo"
        exit 1
    fi
fi

# Префикс для команд (sudo или пусто в зависимости от прав)
SUDO=""
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
fi

# Обновление списка пакетов
echo "Обновление списка пакетов..."
$SUDO apt-get update -y

# Установка зависимостей
echo "Установка зависимостей..."
$SUDO apt-get install -y python3-pip python3-dev build-essential curl net-tools

# Установка Glances через apt
echo "Установка Glances через apt (рекомендуемый метод)..."
$SUDO apt-get install -y glances

# Проверка установки
if ! command -v glances &>/dev/null; then
    echo "Ошибка! Glances не был установлен через apt. Пробуем установить через pip..."
    $SUDO pip3 install glances
    
    if ! command -v glances &>/dev/null; then
        # Создаем обертку для glances, если он установлен, но не доступен в PATH
        GLANCES_PATH=$($SUDO find /usr -name glances 2>/dev/null | grep -v "__pycache__" | head -n 1)
        
        if [ -n "$GLANCES_PATH" ]; then
            echo "Найден путь к Glances: $GLANCES_PATH, создаем ссылку..."
            $SUDO ln -sf "$GLANCES_PATH" /usr/local/bin/glances
        else
            echo "Критическая ошибка! Не удалось найти исполняемый файл glances после установки."
            exit 1
        fi
    fi
fi

# Проверка, доступна ли команда glances
echo "Проверка установки Glances..."
if ! command -v glances &>/dev/null; then
    echo "Ошибка! Не удалось установить Glances. Пожалуйста, проверьте журнал ошибок."
    exit 1
fi

# Определение версии Glances
GLANCES_VERSION=$(glances --version 2>/dev/null || echo "Unknown")
echo "Установлена версия Glances: $GLANCES_VERSION"

# Создание systemd service
echo "Создание и настройка systemd сервиса..."

# Определение полного пути к исполняемому файлу glances
GLANCES_EXEC=$(which glances)

cat << EOF > /tmp/glances.service
[Unit]
Description=Glances Server
After=network.target

[Service]
ExecStart=$GLANCES_EXEC -w --port 61208 --disable-plugin sensors --enable-history
Restart=on-failure
Type=simple
User=root

[Install]
WantedBy=multi-user.target
EOF

# Копирование файла сервиса
$SUDO cp /tmp/glances.service /etc/systemd/system/
$SUDO chmod 644 /etc/systemd/system/glances.service

# Перезагрузка systemd, включение и запуск сервиса
echo "Запуск сервиса Glances..."
$SUDO systemctl daemon-reload
$SUDO systemctl enable glances.service
$SUDO systemctl restart glances.service

# Проверка статуса сервиса
echo "Проверка статуса сервиса..."
$SUDO systemctl status glances.service --no-pager || true

# Проверка, слушает ли сервис порт
sleep 3
if netstat -tulpn 2>/dev/null | grep -q ":61208" || ss -tulpn | grep -q ":61208"; then
    echo "Glances успешно запущен и слушает порт 61208"
else
    echo "Предупреждение: Glances, возможно, не слушает порт 61208. Проверьте журналы systemd для подробностей."
    $SUDO journalctl -u glances -n 20 --no-pager || true
fi

# Проверка доступности API
echo "Проверка доступности API Glances..."
if curl -s http://localhost:61208/api/4/cpu > /dev/null; then
    echo "API Glances успешно отвечает!"
else
    echo "Предупреждение: API Glances не отвечает на localhost. Возможно, он настроен только на сетевой интерфейс."
    
    # Пробуем через IP сервера
    SERVER_IP=$(hostname -I | awk '{print $1}')
    if [ -n "$SERVER_IP" ] && curl -s "http://$SERVER_IP:61208/api/4/cpu" > /dev/null; then
        echo "API Glances доступен через IP сервера: $SERVER_IP"
    else
        echo "Предупреждение: API Glances не отвечает. Возможно, он еще инициализируется."
    fi
fi

echo "Установка Glances завершена."
exit 0