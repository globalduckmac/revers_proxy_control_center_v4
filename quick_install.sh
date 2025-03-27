#!/bin/bash
# Скрипт быстрой установки Reverse Proxy Control Center v3
# Просто запустите:
# wget -O - https://raw.githubusercontent.com/globalduckmac/revers_proxy_control_center_v3/main/quick_install.sh | sudo bash

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}[INFO]${NC} Начинаем установку Reverse Proxy Control Center v3..."

# Проверяем, запущен ли скрипт от имени root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Пожалуйста, запустите скрипт от имени администратора"
    echo -e "Используйте команду: wget -O - https://raw.githubusercontent.com/globalduckmac/revers_proxy_control_center_v3/main/quick_install.sh | sudo bash"
    exit 1
fi

# Устанавливаем git
echo -e "${GREEN}[INFO]${NC} Установка git..."
apt-get update
apt-get install -y git

# Создаем временную директорию
TEMP_DIR=$(mktemp -d)
cd $TEMP_DIR

# Клонируем репозиторий
echo -e "${GREEN}[INFO]${NC} Загрузка установщика..."
git clone https://github.com/globalduckmac/revers_proxy_control_center_v3.git
cd revers_proxy_control_center_v3

# Запускаем установщик
echo -e "${GREEN}[INFO]${NC} Запуск установщика..."
chmod +x install.sh
./install.sh

# Чистим за собой
cd /
rm -rf $TEMP_DIR