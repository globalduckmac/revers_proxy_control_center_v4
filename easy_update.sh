#!/bin/bash
# Скрипт для простого обновления Reverse Proxy Control Center
# Скачивает последнюю версию из GitHub и устанавливает ее
# Использование: bash easy_update.sh

# Настройка цветного вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Простое обновление Reverse Proxy Control Center ===${NC}"
echo "Дата и время: $(date)"
echo "========================================="

# Создаем временную директорию для загрузки
TEMP_DIR=$(mktemp -d)
echo "Создана временная директория: $TEMP_DIR"

# Загружаем последнюю версию из GitHub
echo -e "\n${YELLOW}[1/4] Загрузка последней версии из GitHub...${NC}"
curl -L -o "$TEMP_DIR/rpcc.zip" https://github.com/globalduckmac/revers_proxy_control_center_v4/archive/refs/heads/main.zip
if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка при загрузке архива. Проверьте подключение к интернету.${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
else
    echo -e "${GREEN}Архив успешно загружен.${NC}"
fi

# Распаковка архива
echo -e "\n${YELLOW}[2/4] Распаковка архива...${NC}"
unzip -q "$TEMP_DIR/rpcc.zip" -d "$TEMP_DIR"
if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка при распаковке архива.${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
else
    echo -e "${GREEN}Архив успешно распакован.${NC}"
fi

# Определение текущей директории установки
INSTALL_DIR=$(pwd)
echo "Текущая директория установки: $INSTALL_DIR"

# Копирование файлов
echo -e "\n${YELLOW}[3/4] Обновление файлов...${NC}"
cp -r "$TEMP_DIR"/revers_proxy_control_center_v4-main/* "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка при копировании файлов.${NC}"
    rm -rf "$TEMP_DIR"
    exit 1
else
    echo -e "${GREEN}Файлы успешно обновлены.${NC}"
fi

# Очистка временной директории
rm -rf "$TEMP_DIR"
echo "Временная директория удалена."

# Перезапуск сервиса, если он запущен через systemd
echo -e "\n${YELLOW}[4/4] Проверка необходимости перезапуска сервисов...${NC}"
if systemctl is-active --quiet rpcc.service; then
    echo "Перезапуск службы RPCC..."
    sudo systemctl restart rpcc.service
    echo -e "${GREEN}Служба RPCC перезапущена.${NC}"
else
    echo "Служба RPCC не запущена через systemd, перезапуск не требуется."
fi

echo -e "\n${GREEN}Обновление завершено!${NC}"
echo "========================================="
