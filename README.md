# Reverse Proxy Control Center v3

Система управления и мониторинга серверами и доменами для обратного прокси.

## Основные возможности

- Мониторинг серверов через Glances API
- Управление серверами и их группами
- Управление доменами и доменными группами
- Проверка NS-записей доменов
- Управление обратным прокси Nginx
- Уведомления через Telegram
- Отслеживание дат оплаты серверов

## Зависимости

- Python 3.8+
- PostgreSQL
- Glances (на мониторируемых серверах)
- Nginx (опционально)

## Установка

### Быстрая установка (в одну команду)

Используйте следующую команду для автоматической установки всей системы:

```bash
wget -O - https://raw.githubusercontent.com/globalduckmac/revers_proxy_control_center_v3/main/quick_install.sh | sudo bash
```

После выполнения скрипта, вы получите логин, пароль и URL для доступа к системе.

### Альтернативная автоматическая установка

Вы также можете использовать стандартный скрипт деплоя:

```bash
wget https://raw.githubusercontent.com/globalduckmac/revers_proxy_control_center_v3/main/deploy_script.sh
chmod +x deploy_script.sh
sudo ./deploy_script.sh
```

### Ручная установка

#### 1. Клонируйте репозиторий

```bash
git clone https://github.com/globalduckmac/revers_proxy_control_center_v3.git
cd revers_proxy_control_center_v3
```

#### 2. Создайте виртуальное окружение и установите зависимости

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3. Настройте переменные окружения

```bash
export DATABASE_URL="postgresql://username:password@localhost/database_name"
export SESSION_SECRET="your_secret_key"
```

Для работы уведомлений через Telegram:
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

#### 4. Запустите приложение

```bash
gunicorn --bind 0.0.0.0:5000 main:app
```

## Документация API

### Мониторинг

- `GET /monitoring/` - Панель мониторинга
- `GET /monitoring/server/{server_id}` - Метрики конкретного сервера
- `GET /monitoring/api/server/{server_id}` - JSON API для получения метрик сервера
- `POST /monitoring/collect/{server_id}` - Запуск сбора метрик для сервера

### Серверы

- `GET /servers/` - Список всех серверов
- `GET /servers/create` - Форма создания сервера
- `POST /servers/create` - Создание нового сервера
- `GET /servers/edit/{server_id}` - Форма редактирования сервера
- `POST /servers/edit/{server_id}` - Обновление информации о сервере

### Группы серверов

- `GET /server-groups/` - Список всех групп серверов
- `GET /server-groups/create` - Форма создания группы серверов
- `POST /server-groups/create` - Создание новой группы серверов

### Домены

- `GET /domains/` - Список всех доменов
- `GET /domains/create` - Форма создания домена
- `POST /domains/create` - Создание нового домена
- `GET /domains/nameservers` - Проверка NS-записей

### Группы доменов

- `GET /domain-groups/` - Список всех групп доменов
- `GET /domain-groups/create` - Форма создания группы доменов
- `POST /domain-groups/create` - Создание новой группы доменов

### Glances

- `GET /glances/` - Мониторинг Glances для всех серверов
- `GET /glances/server/{server_id}` - Детальный мониторинг сервера через Glances

## Обновления в этой версии

- Удалена интеграция с MQTT для мониторинга серверов
- Удален мониторинг доменов через SSH
- Оставлен только мониторинг серверов через Glances API
- Обновлены планировщики задач и контроллеры
- Добавлены предупреждения в местах, где функциональность была отключена
- Улучшены скрипты установки с автоматической генерацией паролей
- Добавлена автоматическая диагностика и инструменты устранения неполадок
- Добавлена улучшенная конфигурация Nginx и Gunicorn для повышения стабильности
- Реализован скрипт быстрой установки в одну команду для простого развертывания

## Примечания

- При первом запуске создается администратор с логином `admin` и случайно сгенерированным паролем (выводится в конце установки)
- Для продакшена обязательно измените все секретные ключи и пароли
- Для работы Glances на каждом мониторируемом сервере должен быть установлен и запущен сервис Glances в режиме веб-сервера (порт 61208)

## Диагностика и устранение неполадок

В системе предусмотрен встроенный инструмент диагностики, который автоматически устанавливается вместе с приложением.

### Использование инструмента диагностики

```bash
sudo rpcc-diagnose
```

Этот инструмент проверит:
- Статус всех необходимых сервисов (RPCC, Nginx, PostgreSQL)
- Доступность сетевых портов
- Наличие и состояние лог-файлов
- Состояние базы данных

### Общие проблемы и их решения

#### Ошибка 502 Bad Gateway

Эта ошибка обычно означает, что Nginx не может соединиться с Gunicorn (основное приложение).

Возможные решения:
1. Перезапустите сервисы:
   ```bash
   sudo systemctl restart reverse_proxy_control_center nginx
   ```
2. Проверьте логи приложения:
   ```bash
   sudo journalctl -u reverse_proxy_control_center -n 50
   ```
3. Проверьте, открыт ли порт 5000:
   ```bash
   nc -z -v -w1 localhost 5000
   ```

#### Приложение не запускается

1. Проверьте статус сервиса:
   ```bash
   sudo systemctl status reverse_proxy_control_center
   ```
2. Проверьте логи запуска:
   ```bash
   sudo journalctl -u reverse_proxy_control_center -n 100
   ```
3. Убедитесь, что база данных работает:
   ```bash
   sudo systemctl status postgresql
   ```

#### Сброс пароля администратора

Если вы забыли пароль администратора, выполните следующую команду:

```bash
cd /opt/reverse_proxy_control_center
sudo -u rpcc python reset_admin_password.py
```

## Лицензия

MIT