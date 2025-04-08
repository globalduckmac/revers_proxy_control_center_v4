#!/bin/bash
# Скрипт для выгрузки изменений на GitHub

echo "=== Выгрузка изменений на GitHub ==="
cd $(dirname $0)

# Настраиваем git конфигурацию
git config --global user.name "globalduckmac"
git config --global user.email "user@example.com"

# Добавляем все измененные файлы
git add modules/proxy_manager.py
git add routes/domains.py
git add templates/domains/edit.html

# Создаем коммит
git commit -m "Feature: Добавлена поддержка развертывания конфигурации Nginx для конкретного домена"

# Обновляем локальный репозиторий
git pull --no-edit origin main || {
    echo "Не удалось получить изменения с GitHub, пробуем альтернативный метод..."
    python3 git_auto_reset.py || python git_auto_reset.py
}

# Отправляем изменения на GitHub
git push origin main

echo "=== Готово ==="
