#!/bin/bash
# Скрипт для выгрузки изменений на GitHub

echo "=== Выгрузка изменений на GitHub ==="
cd $(dirname $0)

# Настраиваем git конфигурацию
git config --global user.name "globalduckmac"
git config --global user.email "user@example.com"

# Добавляем все измененные файлы
git add modules/proxy_manager.py

# Создаем коммит
git commit -m "Fix: Исправлена проблема с пустыми файлами конфигурации при фоновом создании"

# Обновляем локальный репозиторий
git pull --no-edit origin main || {
    echo "Не удалось получить изменения с GitHub, пробуем альтернативный метод..."
    python3 git_auto_reset.py || python git_auto_reset.py
}

# Отправляем изменения на GitHub
git push origin main

echo "=== Готово ==="