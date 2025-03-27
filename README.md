# Reverse Proxy Control Center (v3)

Система для управления обратным прокси, настройки доменов и мониторинга серверов.

## Возможности

- Управление серверами и доменами
- Мониторинг состояния серверов через Glances API
- Интеграция с FFPanel
- Группировка серверов и доменов
- Настройка Nginx и SSL-сертификатов
- Мониторинг NS-записей доменов
- Уведомления через Telegram
- Отслеживание платежей и биллинга

## Системные требования

- Ubuntu 20.04+ или Debian 11+
- Python 3.8+
- PostgreSQL 12+
- Nginx
- Glances (устанавливается автоматически)

## Установка

Для установки выполните следующую команду:

```bash
wget -O install.sh https://raw.githubusercontent.com/globalduckmac/revers_proxy_control_center_v3/main/deploy_script_v3.sh && chmod +x install.sh && sudo ./install.sh
```

После установки панель управления будет доступна по адресу `http://ваш_сервер_ip`.
Логин: `admin@example.com`
Пароль: `admin123`

## Структура проекта

- `app.py` - Основной файл приложения
- `models.py` - Модели базы данных
- `routes/` - Маршруты и представления
- `modules/` - Модули для работы с серверами и доменами
- `templates/` - Шаблоны интерфейса
- `scripts/` - Вспомогательные скрипты

## Мониторинг через Glances API

Все серверы контролируются через Glances API (порт 61208), которое собирает следующие метрики:
- Загрузка CPU
- Использование памяти
- Нагрузка на диск
- Сетевая активность

## Интеграция с FFPanel

Панель позволяет синхронизировать домены с FFPanel через открытый API:
- Импорт доменов из FFPanel
- Настройка разных target IP для обратного прокси и FFPanel

## Обслуживание

Для перезапуска сервиса:
```bash
sudo systemctl restart reverse_proxy_manager
```

Для проверки состояния сервиса:
```bash
sudo systemctl status reverse_proxy_manager
```

## Обновление

Для обновления системы до последней версии:
```bash
cd /opt/reverse_proxy_manager && sudo git pull && sudo systemctl restart reverse_proxy_manager
```