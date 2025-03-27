#!/bin/bash

# Скрипт для установки Glances на Ubuntu 22.04
# и настройки его как системного сервиса

set -e

# Цветовое оформление
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
    exit 1
}

# Проверка root прав
if [ "$EUID" -ne 0 ]; then
    error "Установка должна выполняться с правами root. Запустите скрипт с sudo."
fi

# Обновление списка пакетов
log "Обновление списка пакетов..."
apt-get update || error "Не удалось обновить список пакетов"

# Установка Glances
log "Установка Glances..."
apt-get install -y glances || error "Не удалось установить Glances"

# Определение пути к исполняемому файлу glances
GLANCES_EXEC=$(which glances)

# Создание systemd сервиса
log "Создание systemd сервиса для Glances..."

cat << EOF > /etc/systemd/system/glances.service
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

chmod 644 /etc/systemd/system/glances.service
systemctl daemon-reload
systemctl enable glances.service
systemctl restart glances.service

# Проверка, что сервис запущен
if systemctl is-active --quiet glances; then
    success "Glances успешно установлен и запущен как systemd сервис"
    log "Glances доступен по адресу: http://$(hostname -I | awk '{print $1}'):61208"
    log "Glances API доступен по адресу: http://$(hostname -I | awk '{print $1}'):61208/api/4"
else
    error "Не удалось запустить сервис Glances"
fi

# Проверка доступности API
log "Проверка доступности Glances API..."
sleep 2
if curl -s http://localhost:61208/api/4/cpu >/dev/null; then
    success "Glances API доступен по адресу http://localhost:61208/api/4"
else
    warning "Glances API недоступен! Проверьте журналы systemd."
fi

exit 0