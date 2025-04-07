#!/bin/bash
# Скрипт для исправления ошибки с вызовом python/python3
# Использование: bash fix_python3.sh

# Настройка цветного вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Исправление скриптов для работы с Python 3 ===${NC}"
echo "Дата и время: $(date)"
echo "========================================="

# Поиск и замена всех вызовов python на python3
echo -e "\n${YELLOW}[1/2] Исправление вызовов Python в скриптах...${NC}"

# Заменяем в Python-файлах
find . -type f -name "*.py" -exec sed -i 's/subprocess.run(\["python"/subprocess.run(["python3"/g' {} \;
find . -type f -name "*.py" -exec sed -i 's/subprocess.run(\["python",/subprocess.run(["python3",/g' {} \;
find . -type f -name "*.py" -exec sed -i "s/subprocess.run(\['python'/subprocess.run(\['python3'/g" {} \;

# Заменяем в Shell-скриптах
find . -type f -name "*.sh" -exec sed -i 's/python /python3 /g' {} \;

# Создаем симлинк для совместимости (если позволяют права)
echo -e "\n${YELLOW}[2/2] Создание симлинка python -> python3...${NC}"
if [ -x "$(command -v python3)" ] && [ ! -x "$(command -v python)" ]; then
    echo "Python3 найден, Python не найден. Пробуем создать симлинк..."
    
    PYTHON3_PATH=$(which python3)
    
    if [ -w /usr/local/bin ]; then
        sudo ln -sf $PYTHON3_PATH /usr/local/bin/python
        echo -e "${GREEN}Симлинк создан: /usr/local/bin/python -> $PYTHON3_PATH${NC}"
    else
        echo -e "${YELLOW}Нет прав для создания системного симлинка.${NC}"
        echo -e "${YELLOW}Вы можете создать локальный симлинк в текущей директории.${NC}"
        ln -sf $PYTHON3_PATH ./python
        echo -e "${GREEN}Локальный симлинк создан: ./python -> $PYTHON3_PATH${NC}"
        echo -e "${YELLOW}Убедитесь, что текущая директория находится в PATH при запуске скриптов.${NC}"
    fi
fi

echo -e "\n${GREEN}Исправление завершено!${NC}"
echo "Теперь все скрипты должны работать с Python 3."
echo "========================================="