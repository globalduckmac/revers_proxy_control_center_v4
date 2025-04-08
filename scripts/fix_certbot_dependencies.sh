#!/bin/bash
#
# Скрипт для исправления зависимостей Certbot
# Устраняет конфликты между urllib3 и requests-toolbelt
#

echo "Fixing Certbot dependencies..."

# Сохраняем текущую директорию
CURRENT_DIR=$(pwd)

# Проверяем наличие pip
if ! command -v pip3 &> /dev/null; then
    echo "Installing pip3..."
    apt-get update
    apt-get install -y python3-pip
fi

# Удаляем конфликтующие пакеты
echo "Removing conflicting packages..."
pip3 uninstall -y requests requests-toolbelt urllib3

# Устанавливаем совместимые версии
echo "Installing compatible versions..."
pip3 install requests==2.25.1
pip3 install urllib3==1.26.6
pip3 install requests-toolbelt==0.9.1

# Проверяем certbot
echo "Testing Certbot..."
if certbot --version &> /dev/null; then
    echo "Certbot is working correctly."
    exit 0
else
    echo "Certbot is still not working, attempting to reinstall..."
    apt-get install --reinstall -y certbot python3-certbot-nginx
    
    if certbot --version &> /dev/null; then
        echo "Certbot reinstalled successfully."
        exit 0
    else
        echo "Failed to fix Certbot. Please try manually reinstalling it."
        exit 1
    fi
fi