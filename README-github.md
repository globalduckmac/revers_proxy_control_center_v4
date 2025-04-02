# Reverse Proxy Control Center v4

Система управления и мониторинга reverse-proxy серверов с поддержкой Glances для мониторинга производительности.

## Основные возможности

- Управление несколькими reverse-proxy серверами через веб-интерфейс
- Автоматическое развертывание и настройка Nginx
- Автоматическая установка и настройка SSL-сертификатов через Let's Encrypt
- Мониторинг состояния серверов через Glances API
- Интеграция с доменными группами
- Поддержка мониторинга внешних серверов без SSH доступа
- Интеграция с FFPanel для управления доменами
- Telegram-оповещения о статусе серверов и доменов

## Требования

- Python 3.8+
- PostgreSQL
- Nginx
- Glances на серверах для мониторинга

## Установка

1. Клонировать репозиторий:
```bash
git clone https://github.com/globalduckmac/revers_proxy_control_center_v4.git
cd revers_proxy_control_center_v4
```

2. Установить зависимости:
```bash
pip install -r requirements-app.txt
```

3. Настроить переменные окружения:
```bash
# Настройки базы данных
export DATABASE_URL="postgresql://username:password@localhost/db_name"

# Секретный ключ сессии
export SESSION_SECRET="your-secret-key"

# Настройки Telegram (опционально)
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
```

4. Инициализировать базу данных:
```bash
python init_db.py
```

5. Создать администратора:
```bash
python create_admin.py
```

6. Запустить приложение:
```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 main:app
```

## Использование Glances для мониторинга

Система использует Glances API для мониторинга производительности серверов. Для настройки Glances на ваших серверах:

1. Установите Glances:
```bash
curl -L https://raw.githubusercontent.com/nicolargo/glancesautoinstall/master/install.sh | sudo /bin/bash
```

2. Настройте Glances как службу systemd:
```bash
sudo tee /etc/systemd/system/glances.service > /dev/null << 'EOF'
[Unit]
Description=Glances
After=network.target

[Service]
ExecStart=/usr/local/bin/glances -w -t 5 --disable-plugin sensors --disable-plugin smart --disable-webui
Restart=on-abort
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable glances
sudo systemctl start glances
```

3. Убедитесь, что порт 61208 доступен для подключения (это порт API Glances по умолчанию).

## Обновление схемы базы данных

Система включает несколько скриптов для обновления схемы базы данных:

- `init_db.py` - Инициализация новой базы данных
- `fix_load_average_field.py` - Исправление длины поля load_average для метрик серверов
- `add_glances_fields.py` - Добавление полей для Glances в модель Server
- `add_server_metric_fields.py` - Добавление дополнительных полей метрик для серверов
- `add_external_server_table.py` - Добавление таблицы для внешних серверов

При обновлении базы данных рекомендуется выполнять скрипты в порядке, соответствующем истории разработки.