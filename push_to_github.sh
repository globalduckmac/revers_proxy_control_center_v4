#!/bin/bash
# Скрипт для выгрузки изменений на GitHub

# Настройка цветного вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Выгрузка изменений на GitHub ===${NC}"
echo "Дата и время: $(date)"
echo "========================================="

# Проверка наличия токена GitHub
if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${RED}Ошибка: Не установлен токен GitHub (GITHUB_TOKEN)${NC}"
    echo "Проверьте наличие переменной окружения GITHUB_TOKEN"
    exit 1
fi

# Настройка локального репозитория
git config --global user.name "globalduckmac"
git config --global user.email "user@example.com"

# Настройка GitHub с токеном
git config --global credential.helper store
echo "https://globalduckmac:${GITHUB_TOKEN}@github.com" > ~/.git-credentials

# Настраиваем remote
git remote -v | grep "https://github.com/globalduckmac/revers_proxy_control_center_v4" > /dev/null
if [ $? -ne 0 ]; then
    # Если нет нужного remote
    echo -e "${YELLOW}Настройка репозитория GitHub...${NC}"
    git remote add github https://github.com/globalduckmac/revers_proxy_control_center_v4.git
else
    echo -e "${GREEN}Репозиторий GitHub уже настроен.${NC}"
fi

# Добавляем изменения
echo -e "\n${YELLOW}Добавление изменений в индекс...${NC}"
# Добавляем исправленные файлы
git add routes/domains.py
git add templates/domains/edit.html
git add routes/settings.py

# Создаем коммит
echo -e "\n${YELLOW}Создание коммита...${NC}"
git commit -m "Исправления: улучшение деплоя домена и обновления из GitHub

- Исправлена проблема с деплоем конфигурации домена через чекбоксы групп
- Добавлено дополнительное логирование в функцию деплоя
- Исправлена проблема с обновлением из GitHub: добавлена поддержка python3"

# Отправляем изменения
echo -e "\n${YELLOW}Отправка изменений в GitHub...${NC}"
if git push github main; then
    echo -e "${GREEN}Изменения успешно отправлены в GitHub!${NC}"
else
    echo -e "${RED}Ошибка при отправке изменений в GitHub${NC}"
    echo "Пробуем pullrebase и повторную отправку..."
    
    if git pull --rebase github main && git push github main; then
        echo -e "${GREEN}Изменения успешно отправлены в GitHub после pull-rebase!${NC}"
    else
        echo -e "${RED}Не удалось отправить изменения в GitHub. Проверьте логи ошибок выше.${NC}"
        exit 1
    fi
fi

echo -e "\n${GREEN}Все операции успешно выполнены!${NC}"
