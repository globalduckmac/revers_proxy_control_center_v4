#!/bin/bash
# Скрипт для простого обновления Reverse Proxy Control Center с GitHub
# Использование: bash update.sh

# Настройка цветного вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Обновление Reverse Proxy Control Center ===${NC}"
echo "Дата и время: $(date)"
echo "========================================="

# Сохраняем текущую директорию
CURRENT_DIR=$(pwd)

# Настройка Git, если требуется
echo -e "\n${YELLOW}[1/4] Настройка Git...${NC}"
git config pull.rebase false
if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка при настройке Git, но продолжаем...${NC}"
fi

# Удаление потенциально неправильных удалённых репозиториев
echo -e "\n${YELLOW}[2/4] Проверка настройки удалённого репозитория...${NC}"
GITHUB_REPO="https://github.com/globalduckmac/revers_proxy_control_center_v4.git"

# Удаление старого remote, если он существует с другим URL
git remote -v | grep origin > /dev/null 2>&1
if [ $? -eq 0 ]; then
    CURRENT_URL=$(git remote get-url origin)
    if [ "$CURRENT_URL" != "$GITHUB_REPO" ]; then
        echo "Обновление URL удалённого репозитория origin..."
        git remote set-url origin "$GITHUB_REPO"
    fi
else
    echo "Добавление удалённого репозитория origin..."
    git remote add origin "$GITHUB_REPO"
fi

# Получение последних изменений
echo -e "\n${YELLOW}[3/4] Получение последних изменений из GitHub...${NC}"
git fetch origin main

# Проверка, есть ли различия между локальной и удаленной версией
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "${GREEN}Система уже обновлена до последней версии.${NC}"
else
    echo "Обнаружены новые изменения в репозитории."
    
    # Пробуем сделать pull
    echo -e "\nПрименение новых изменений..."
    git pull origin main
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка при обновлении через git pull.${NC}"
        echo -e "${YELLOW}Пробуем альтернативный метод обновления...${NC}"
        
        # Альтернативный метод - сброс к состоянию удаленного репозитория
        git reset --hard origin/main
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}Не удалось обновить систему. Пожалуйста, свяжитесь с администратором.${NC}"
            exit 1
        else
            echo -e "${GREEN}Система успешно обновлена методом сброса.${NC}"
        fi
    else
        echo -e "${GREEN}Система успешно обновлена.${NC}"
    fi
fi

# Перезапуск сервисов, если они работают через systemd
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