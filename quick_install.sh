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

# Устанавливаем необходимые зависимости
echo -e "${GREEN}[INFO]${NC} Установка необходимых зависимостей..."
apt-get update
apt-get install -y git netcat curl wget

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

# Проверяем статус установки
echo -e "${GREEN}[INFO]${NC} Проверка статуса установки..."
sleep 3

# Проверка доступности системных сервисов
echo -e "\n${GREEN}[ПРОВЕРКА]${NC} Проверка состояния сервисов..."
systemctl is-active --quiet postgresql && echo -e "PostgreSQL: ${GREEN}активен${NC}" || echo -e "PostgreSQL: ${RED}не активен${NC}"
systemctl is-active --quiet nginx && echo -e "Nginx: ${GREEN}активен${NC}" || echo -e "Nginx: ${RED}не активен${NC}"
systemctl is-active --quiet reverse_proxy_control_center && echo -e "RPCC: ${GREEN}активен${NC}" || echo -e "RPCC: ${RED}не активен${NC}"

# Проверка сетевой доступности
echo -e "\n${GREEN}[ПРОВЕРКА]${NC} Проверка сетевых портов..."
nc -z -v -w1 localhost 5000 >/dev/null 2>&1 && echo -e "Порт 5000 (Gunicorn): ${GREEN}открыт${NC}" || echo -e "Порт 5000 (Gunicorn): ${RED}закрыт${NC}"
nc -z -v -w1 localhost 80 >/dev/null 2>&1 && echo -e "Порт 80 (Nginx): ${GREEN}открыт${NC}" || echo -e "Порт 80 (Nginx): ${RED}закрыт${NC}"
nc -z -v -w1 localhost 5432 >/dev/null 2>&1 && echo -e "Порт 5432 (PostgreSQL): ${GREEN}открыт${NC}" || echo -e "Порт 5432 (PostgreSQL): ${RED}закрыт${NC}"

echo -e "\n${GREEN}[СОВЕТ]${NC} Если у вас возникли проблемы с доступом к веб-интерфейсу, выполните команду:"
echo -e "  sudo rpcc-diagnose"
echo -e "Эта команда предоставит подробную информацию о состоянии системы и возможных проблемах.\n"

# Чистим за собой
cd /
rm -rf $TEMP_DIR

echo -e "${GREEN}[ГОТОВО]${NC} Установка завершена! Если у вас возникли проблемы, обратитесь к документации или выполните диагностику с помощью команды 'sudo rpcc-diagnose'."