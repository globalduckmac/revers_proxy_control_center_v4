import logging
import time
import threading
import pytz
from datetime import datetime, timedelta

from app import db
from models import Server, Domain, DomainGroup, ExternalServer
from modules.domain_manager import DomainManager
from modules.telegram_notifier import TelegramNotifier
from modules.glances_manager import GlancesManager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Интервалы выполнения задач (в секундах)
CHECK_SERVER_INTERVAL = 300  # 5 минут - мониторинг серверов только через Glances API
CHECK_DOMAIN_NS_INTERVAL = 3600  # 1 час
COLLECT_SERVER_METRICS_INTERVAL = 300  # 5 минут - сбор метрик только через Glances API
DAILY_REPORT_INTERVAL = 86400  # 24 часа
PAYMENT_REMINDER_INTERVAL = 43200  # 12 часов
CHECK_EXTERNAL_SERVER_INTERVAL = 300  # 5 минут - мониторинг внешних серверов через Glances API

class BackgroundTasks:
    """
    Класс для управления фоновыми задачами в системе.
    """
    def __init__(self):
        self.is_running = False
        self.tasks = []
        
    def _mask_ip_address(self, ip_address):
        """
        Маскирует IP-адрес, оставляя только первую часть видимой
        
        Args:
            ip_address (str): IP-адрес для маскировки
            
        Returns:
            str: Маскированный IP-адрес
        """
        if not ip_address:
            return "неизвестно"
            
        try:
            # Разбиваем IP-адрес на части
            parts = ip_address.split('.')
            if len(parts) == 4:  # IPv4
                # Оставляем первый октет, остальные заменяем на X
                return f"{parts[0]}.X.X.X"
            else:
                # Для других форматов адресов просто возвращаем первую часть
                return f"{parts[0]}.***(скрыто)"
        except Exception:
            # В случае ошибки возвращаем безопасное значение
            return "X.X.X.X"
    
    def start(self):
        """
        Запускает все фоновые задачи.
        """
        if self.is_running:
            logger.warning("Задачи уже запущены")
            return
        
        self.is_running = True
        logger.info("Запуск фоновых задач...")
        
        # Очистка старых задач
        self.tasks = []
        
        # Создание и запуск задач
        self.tasks.append(
            threading.Thread(
                target=self._run_task,
                args=(self._check_servers, CHECK_SERVER_INTERVAL, "Проверка серверов через Glances API"),
                daemon=True
            )
        )
        
        self.tasks.append(
            threading.Thread(
                target=self._run_task,
                args=(self._check_domains_ns, CHECK_DOMAIN_NS_INTERVAL, "Проверка NS доменов"),
                daemon=True
            )
        )
        
        self.tasks.append(
            threading.Thread(
                target=self._run_task,
                args=(self._collect_server_metrics, COLLECT_SERVER_METRICS_INTERVAL, "Сбор метрик серверов"),
                daemon=True
            )
        )
        
        self.tasks.append(
            threading.Thread(
                target=self._run_task,
                args=(self._send_daily_report, DAILY_REPORT_INTERVAL, "Ежедневный отчет"),
                daemon=True
            )
        )
        
        self.tasks.append(
            threading.Thread(
                target=self._run_task,
                args=(self._check_payment_reminders, PAYMENT_REMINDER_INTERVAL, "Проверка платежей"),
                daemon=True
            )
        )
        
        # Добавляем новую задачу для проверки внешних серверов
        self.tasks.append(
            threading.Thread(
                target=self._run_task,
                args=(self._check_external_servers, CHECK_EXTERNAL_SERVER_INTERVAL, "Проверка внешних серверов"),
                daemon=True
            )
        )
        
        # Запуск всех задач
        for task in self.tasks:
            task.start()
        
        logger.info(f"Запущено {len(self.tasks)} фоновых задач")
    
    def stop(self):
        """
        Останавливает все фоновые задачи.
        """
        self.is_running = False
        logger.info("Остановка фоновых задач...")
        
        # Ждем завершения всех задач
        for task in self.tasks:
            if task.is_alive():
                task.join(1)  # таймаут 1 секунда
        
        self.tasks = []
        logger.info("Все фоновые задачи остановлены")
    
    def _run_task(self, task_func, interval, task_name):
        """
        Запускает задачу с заданным интервалом.
        
        Args:
            task_func: Функция задачи
            interval: Интервал выполнения в секундах
            task_name: Название задачи для логирования
        """
        logger.info(f"Запуск задачи: {task_name} (интервал: {interval} сек)")
        
        # Получаем экземпляр приложения Flask для использования в контексте
        from app import app
        
        while self.is_running:
            try:
                start_time = time.time()
                logger.info(f"Выполнение задачи: {task_name}")
                
                # Выполнение задачи внутри контекста приложения Flask
                with app.app_context():
                    # Выполнение задачи
                    task_func()
                
                # Расчет времени выполнения
                execution_time = time.time() - start_time
                logger.info(f"Задача {task_name} выполнена за {execution_time:.2f} сек")
                
                # Ожидание до следующего запуска с учетом времени выполнения
                sleep_time = max(0, interval - execution_time)
                logger.debug(f"Ожидание {sleep_time:.2f} сек до следующего запуска задачи {task_name}")
                
                # Проверка флага is_running каждую секунду для быстрой остановки
                for _ in range(int(sleep_time)):
                    if not self.is_running:
                        break
                    time.sleep(1)
                
                # Остаток времени
                time.sleep(sleep_time - int(sleep_time))
                
            except Exception as e:
                logger.error(f"Ошибка в задаче {task_name}: {str(e)}")
                time.sleep(10)  # пауза в случае ошибки
    
    def _run_scheduled_task(self, task_func, task_name):
        """
        Запускает задачу по расписанию (например, каждый день в определенное время).
        
        Args:
            task_func: Функция задачи
            task_name: Название задачи для логирования
        """
        logger.info(f"Запуск задачи по расписанию: {task_name}")
        
        # Получаем экземпляр приложения Flask для использования в контексте
        from app import app
        
        while self.is_running:
            try:
                # Получаем текущее время
                now = datetime.now()
                
                # Вычисляем время следующего запуска (например, 3 часа ночи)
                next_run = datetime(now.year, now.month, now.day, 3, 0, 0)
                if next_run <= now:
                    # Если текущее время уже больше запланированного, переходим на следующий день
                    next_run += timedelta(days=1)
                
                # Вычисляем время до следующего запуска
                seconds_until_next_run = (next_run - now).total_seconds()
                
                logger.info(f"Следующий запуск задачи {task_name}: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                           f"(через {seconds_until_next_run:.0f} сек)")
                
                # Ожидание до следующего запуска с периодической проверкой флага is_running
                while seconds_until_next_run > 0 and self.is_running:
                    sleep_time = min(60, seconds_until_next_run)  # Проверка каждую минуту или меньше
                    time.sleep(sleep_time)
                    seconds_until_next_run -= sleep_time
                    
                    # Обновляем время до следующего запуска
                    now = datetime.now()
                    seconds_until_next_run = (next_run - now).total_seconds()
                
                if self.is_running:
                    # Выполнение задачи
                    start_time = time.time()
                    logger.info(f"Выполнение задачи по расписанию: {task_name}")
                    
                    # Выполнение задачи внутри контекста приложения Flask
                    with app.app_context():
                        task_func()
                        
                    execution_time = time.time() - start_time
                    logger.info(f"Задача {task_name} выполнена за {execution_time:.2f} сек")
                
            except Exception as e:
                logger.error(f"Ошибка в задаче по расписанию {task_name}: {str(e)}")
                time.sleep(10)  # пауза в случае ошибки
    
    def _check_servers(self):
        """
        Проверяет доступность серверов и их сервисов.
        Использует только Glances API для мониторинга (без SSH).
        """
        try:
            # Импортируем db для работы с базой данных
            from app import db
            from models import ServerLog
            import requests
            import time

            # Получаем все активные серверы
            servers = Server.query.filter_by(is_active=True).all()
            logger.info(f"Проверка {len(servers)} серверов через Glances API")
            
            for server in servers:
                try:
                    # Проверяем только через Glances API (порт 61208 стандартный)
                    # Обратите внимание: мы не проверяем glances_enabled, чтобы обеспечить 
                    # проверку всех серверов, даже если пользователь случайно отключил Glances
                    
                    try:
                        # Прямая проверка Glances API без входа на сервер
                        glances_url = f"http://{server.ip_address}:61208/api/4/all"
                        response = requests.get(glances_url, timeout=5)
                        
                        if response.status_code == 200:
                            # Запрос выполнен успешно
                            server.glances_available = True
                            server.glances_installed = True
                            server.glances_status = "active"
                            server.glances_port = 61208
                            server.last_status = "online"
                            server.last_check = datetime.utcnow()
                            # Принудительно обновляем статус сервера на активный, даже если SSH недоступен
                            old_status = server.status
                            server.status = 'active'  # Устанавливаем активный статус сервера, если API доступен
                            
                            # Сохраняем метрики
                            data = response.json()
                            
                            # CPU
                            if 'cpu' in data:
                                cpu_usage = data['cpu']['total']
                                server.glances_cpu = cpu_usage
                                
                                # Проверка на высокую загрузку CPU
                                if cpu_usage > 80:  # Высокая загрузка CPU
                                    self._check_high_load_metrics(server, f"CPU: {cpu_usage}%")
                            
                            # Memory
                            if 'mem' in data:
                                mem_usage = data['mem']['percent']
                                server.glances_memory = mem_usage
                                
                                # Проверка на высокую загрузку памяти
                                if mem_usage > 90:  # Высокая загрузка памяти
                                    self._check_high_load_metrics(server, f"RAM: {mem_usage}%")
                            
                            # Disk
                            if 'fs' in data and len(data['fs']) > 0:
                                import json
                                disks_info = []
                                for disk in data['fs']:
                                    disks_info.append({
                                        'device': disk['device_name'],
                                        'mountpoint': disk['mnt_point'],
                                        'percent': disk['percent']
                                    })
                                    
                                    # Проверка на высокую загрузку диска
                                    if disk['percent'] > 90:
                                        mountpoint = disk.get('mnt_point', 'неизвестно')
                                        self._check_high_load_metrics(
                                            server, 
                                            f"Диск {mountpoint}: {disk['percent']}% использовано"
                                        )
                                
                                server.glances_disk = json.dumps(disks_info)
                            
                            # Network
                            if 'network' in data:
                                import json
                                networks_info = []
                                # Проверяем формат данных сети (словарь или список)
                                if isinstance(data['network'], dict):
                                    # Стандартный формат - словарь интерфейсов
                                    for name, netif in data['network'].items():
                                        if name not in ['lo', 'total']:
                                            networks_info.append({
                                                'interface': name,
                                                'rx': netif.get('rx', 0),
                                                'tx': netif.get('tx', 0)
                                            })
                                else:
                                    # Альтернативный формат - список интерфейсов
                                    logger.warning("Network data is in list format, adapting processing...")
                                    try:
                                        for item in data['network']:
                                            if isinstance(item, dict):
                                                interface_name = item.get('interface_name', 'unknown')
                                                if interface_name not in ['lo', 'total']:
                                                    networks_info.append({
                                                        'interface': interface_name,
                                                        'rx': item.get('rx', 0),
                                                        'tx': item.get('tx', 0)
                                                    })
                                    except Exception as e:
                                        logger.error(f"Error processing network list data: {str(e)}")
                                
                                server.glances_network = json.dumps(networks_info)
                            
                            # Load average
                            if 'load' in data:
                                server.glances_load = f"{data['load']['min1']}, {data['load']['min5']}, {data['load']['min15']}"
                            
                            # Uptime
                            if 'uptime' in data:
                                # Проверяем формат uptime - может прийти как число или как строка
                                uptime_value = data['uptime']
                                if isinstance(uptime_value, str):
                                    # Если строка в формате "ЧЧ:ММ:СС", конвертируем в секунды
                                    try:
                                        if ":" in uptime_value:
                                            parts = uptime_value.split(":")
                                            if len(parts) == 3:  # формат "ЧЧ:ММ:СС"
                                                hours, minutes, seconds = parts
                                                total_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
                                                server.glances_uptime = total_seconds
                                            elif len(parts) == 2:  # формат "ММ:СС"
                                                minutes, seconds = parts
                                                total_seconds = int(minutes) * 60 + int(seconds)
                                                server.glances_uptime = total_seconds
                                            else:
                                                # Если формат неизвестен, сохраняем 0
                                                logger.warning(f"Неизвестный формат uptime: {uptime_value}, устанавливаем 0")
                                                server.glances_uptime = 0
                                        else:
                                            # Пробуем преобразовать строку в число
                                            server.glances_uptime = int(float(uptime_value))
                                    except (ValueError, TypeError) as e:
                                        logger.warning(f"Ошибка преобразования uptime '{uptime_value}': {str(e)}, устанавливаем 0")
                                        server.glances_uptime = 0
                                else:
                                    # Если это число, сохраняем как есть
                                    try:
                                        server.glances_uptime = int(uptime_value)
                                    except (ValueError, TypeError):
                                        logger.warning(f"Не удалось преобразовать uptime {uptime_value} в целое число, устанавливаем 0")
                                        server.glances_uptime = 0
                                
                            # Проверяем, был ли изменен статус с offline на online
                            old_status = server.status
                            server.status = 'active'
                            
                            # Сохраняем изменения
                            db.session.commit()
                            logger.info(f"Сервер {server.name} доступен, метрики обновлены")
                            
                            # Отправляем уведомление в Telegram ТОЛЬКО если статус изменился с offline на online
                            if old_status != 'active':
                                # Маскируем IP-адрес для уведомления
                                masked_ip = self._mask_ip_address(server.ip_address)
                                
                                TelegramNotifier.send_alert(
                                    f"✅ Сервер {server.name} ({masked_ip}) снова доступен!\n"
                                    f"Glances API работает."
                                )
                            
                        else:
                            # API недоступен
                            old_status = server.status
                            server.glances_available = False
                            server.status = 'error'
                            server.last_status = "offline"
                            server.last_check = datetime.utcnow()
                            
                            # Логируем недоступность Glances API
                            log = ServerLog(
                                server_id=server.id,
                                action="glances_check",
                                status="error",
                                message=f"Glances API недоступен на сервере {server.name}. Код ответа: {response.status_code}"
                            )
                            db.session.add(log)
                            db.session.commit()
                            
                            # Отправляем уведомление в Telegram ТОЛЬКО если статус изменился с online на offline
                            if old_status != 'error':
                                # Маскируем IP-адрес для уведомления
                                masked_ip = self._mask_ip_address(server.ip_address)
                                
                                TelegramNotifier.send_alert(
                                    f"❌ Сервер {server.name} ({masked_ip}) недоступен!\n"
                                    f"Glances API не отвечает. Код: {response.status_code}"
                                )
                    except requests.exceptions.Timeout:
                        # Тайм-аут соединения
                        old_status = server.status
                        server.glances_available = False
                        server.status = 'error'
                        server.last_status = "timeout"
                        server.last_check = datetime.utcnow()
                        
                        # Логируем тайм-аут
                        log = ServerLog(
                            server_id=server.id,
                            action="glances_check",
                            status="error",
                            message=f"Тайм-аут при подключении к Glances API на сервере {server.name}"
                        )
                        db.session.add(log)
                        db.session.commit()
                        
                        # Отправляем уведомление в Telegram ТОЛЬКО если статус изменился
                        if old_status != 'error':
                            # Маскируем IP-адрес для уведомления
                            masked_ip = self._mask_ip_address(server.ip_address)
                            
                            TelegramNotifier.send_alert(
                                f"⚠️ Сервер {server.name} ({masked_ip}) не отвечает!\n"
                                f"Тайм-аут при подключении к Glances API."
                            )
                    except Exception as e:
                        # Другие ошибки
                        old_status = server.status
                        server.glances_available = False
                        server.status = 'error'
                        server.last_status = "error"
                        server.last_check = datetime.utcnow()
                        
                        logger.error(f"Ошибка при проверке Glances API на сервере {server.name}: {str(e)}")
                        
                        # Логируем ошибку
                        log = ServerLog(
                            server_id=server.id,
                            action="glances_check",
                            status="error",
                            message=f"Ошибка при проверке Glances API: {str(e)}"
                        )
                        db.session.add(log)
                        db.session.commit()
                        
                        # Отправляем уведомление в Telegram ТОЛЬКО если статус изменился
                        if old_status != 'error':
                            # Маскируем IP-адрес для уведомления
                            masked_ip = self._mask_ip_address(server.ip_address)
                            
                            TelegramNotifier.send_alert(
                                f"❌ Сервер {server.name} ({masked_ip}) недоступен!\n"
                                f"Ошибка при проверке Glances API: {str(e)[:100]}..."  # Обрезаем длинные сообщения об ошибках
                            )
                    
                    # Обновляем информацию о сервере
                    db.session.commit()
                    
                    # Добавляем небольшую задержку между запросами к серверам
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Ошибка при проверке сервера {server.name}: {str(e)}")
            
            # Также проверяем внешние серверы 
            logger.info("Проверка внешних серверов...")
            GlancesManager.check_all_external_servers()
            
            logger.info("Проверка серверов завершена")
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка серверов: {str(e)}")
    
    def _check_domains_ns(self):
        """
        Проверяет NS записи доменов на соответствие ожидаемым значениям.
        Использует DomainManager.check_all_domains_ns_status для правильной проверки с учетом подстрок.
        """
        try:
            # Получаем все активные домены с ожидаемыми NS
            from models import Domain
            domains = Domain.query.filter(
                Domain.is_active == True,
                Domain.expected_nameservers.isnot(None)
            ).all()
            logger.info(f"Проверка NS записей для {len(domains)} доменов")
            
            # Используем метод DomainManager, который правильно обрабатывает подстроки
            # и сам обновляет статусы в базе данных
            from modules.domain_manager import DomainManager
            
            # Запускаем проверку всех доменов. Параметр web_request=False означает, 
            # что это фоновая проверка и не нужно уменьшать задержки для быстрого ответа.
            results = DomainManager.check_all_domains_ns_status(web_request=False)
            
            # После проверки записываем информацию в журнал
            logger.info(f"Автоматическая проверка NS статусов завершена. Результаты: ok={results['ok']}, mismatch={results['mismatch']}, error={results['error']}")
            
            # Добавляем запись в системный журнал
            from models import ServerLog
            from app import db
            activity_log = ServerLog(
                server_id=None,  # Используем None для общесистемных событий
                action='domain_ns_check_batch_auto',
                status='success',
                message=f"Выполнена автоматическая проверка NS-записей для {len(domains)} доменов. "
                        f"Результаты: ok={results['ok']}, mismatch={results['mismatch']}, error={results['error']}"
            )
            db.session.add(activity_log)
            db.session.commit()
            
            # Перезагрузка каскада уведомлений о смене статуса происходит
            # автоматически в методе check_domain_ns_status класса DomainManager
            logger.info("Проверка NS записей завершена")
            
        except Exception as e:
            logger.error(f"Ошибка при проверке NS записей доменов: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                from app import db
                db.session.rollback()
            except Exception as rollback_error:
                logger.error(f"Ошибка при откате транзакции: {str(rollback_error)}")
    
    def _collect_server_metrics(self):
        """
        Собирает метрики с серверов через Glances API.
        """
        try:
            # Импортируем db для работы с базой данных
            from app import db
            import time
            
            # Получаем все активные серверы с включенным Glances
            servers = Server.query.filter_by(is_active=True, glances_enabled=True).all()
            logger.info(f"Сбор метрик с {len(servers)} серверов через Glances API")
            
            for server in servers:
                try:
                    # Сбор метрик через Glances API
                    GlancesManager.check_glances(server)
                    # Добавляем небольшую задержку между запросами к серверам
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(f"Ошибка при сборе метрик с сервера {server.name}: {str(e)}")
            
            # Фиксируем изменения в базе данных
            db.session.commit()
            
            # Также собираем метрики для внешних серверов
            try:
                from models import ExternalServer
                # Получаем все активные внешние серверы
                external_servers = ExternalServer.query.filter_by(is_active=True).all()
                logger.info(f"Сбор метрик с {len(external_servers)} внешних серверов")
                
                for server in external_servers:
                    try:
                        # Обновляем метрики внешнего сервера
                        GlancesManager.update_external_server_metrics(server)
                        # Добавляем небольшую задержку между запросами к серверам
                        time.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Ошибка при сборе метрик с внешнего сервера {server.name}: {str(e)}")
                
                # Фиксируем изменения в базе данных
                db.session.commit()
            except Exception as e:
                logger.error(f"Ошибка при получении списка внешних серверов: {str(e)}")
            
            logger.info("Сбор метрик серверов завершен")
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка серверов для сбора метрик: {str(e)}")
    
    def _collect_domain_metrics(self):
        """
        Собирает метрики по доменам (количество активных, с проблемами NS и т.д.)
        """
        pass
    
    def _send_daily_report(self):
        """
        Отправляет ежедневный отчет о состоянии системы в Telegram.
        Использует метод TelegramNotifier.send_daily_report вместо создания отдельного отчета.
        """
        try:
            import asyncio
            from modules.telegram_notifier import TelegramNotifier
            
            # Вызываем асинхронную функцию в синхронном контексте
            asyncio.run(TelegramNotifier.send_daily_report())
            
            logger.info("Ежедневный отчет отправлен")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке ежедневного отчета: {str(e)}")
    
    def _check_payment_reminders(self):
        """
        Проверяет серверы на приближение даты оплаты и отправляет уведомления.
        """
        try:
            logger.info("Проверка напоминаний об оплате серверов")
            
            # Установка временной зоны
            tz = pytz.timezone('Europe/Moscow')
            now = datetime.now(tz)
            
            # Получаем все активные серверы с датой оплаты
            servers = Server.query.filter(
                Server.is_active == True,
                Server.payment_date != None
            ).all()
            
            logger.info(f"Найдено {len(servers)} серверов с датой оплаты")
            
            for server in servers:
                try:
                    # Проверяем, есть ли дата оплаты
                    if not server.payment_date:
                        continue
                    
                    # Преобразуем дату оплаты в datetime с учетом временной зоны
                    payment_date = datetime.combine(server.payment_date, datetime.min.time())
                    payment_date = tz.localize(payment_date)
                    
                    # Вычисляем разницу в днях
                    days_left = (payment_date - now).days
                    
                    # Если осталось менее 3 дней до оплаты, отправляем уведомление
                    if 0 <= days_left <= 3:
                        # Маскируем IP-адрес для уведомления
                        masked_ip = self._mask_ip_address(server.ip_address)
                        
                        # Отправляем уведомление в Telegram
                        TelegramNotifier.send_alert(
                            f"💰 Напоминание об оплате!\n\n"
                            f"Сервер: {server.name}\n"
                            f"IP: {masked_ip}\n"
                            f"Дата оплаты: {server.payment_date.strftime('%d.%m.%Y')}\n"
                            f"Осталось дней: {days_left}\n"
                            f"Сумма: {server.payment_amount or 'не указана'}\n"
                            f"Комментарий: {server.comment or 'нет'}"
                        )
                        
                        logger.info(f"Отправлено напоминание об оплате сервера {server.name}")
                    
                    # Если дата оплаты прошла, также отправляем уведомление
                    if days_left < 0:
                        # Маскируем IP-адрес для уведомления
                        masked_ip = self._mask_ip_address(server.ip_address)
                        
                        # Отправляем уведомление в Telegram
                        TelegramNotifier.send_alert(
                            f"⚠️ Просрочена оплата!\n\n"
                            f"Сервер: {server.name}\n"
                            f"IP: {masked_ip}\n"
                            f"Дата оплаты: {server.payment_date.strftime('%d.%m.%Y')}\n"
                            f"Просрочено дней: {abs(days_left)}\n"
                            f"Сумма: {server.payment_amount or 'не указана'}\n"
                            f"Комментарий: {server.comment or 'нет'}"
                        )
                        
                        logger.info(f"Отправлено уведомление о просрочке оплаты сервера {server.name}")
                
                except Exception as e:
                    logger.error(f"Ошибка при проверке оплаты сервера {server.name}: {str(e)}")
            
            logger.info("Проверка напоминаний об оплате завершена")
            
        except Exception as e:
            logger.error(f"Ошибка при проверке напоминаний об оплате: {str(e)}")
    
    def _check_high_load_metrics(self, server, metric):
        """
        Обрабатывает случаи высокой нагрузки на сервер.
        
        Args:
            server: Объект сервера
            metric: Строка с описанием метрики, превысившей пороговое значение
        """
        logger.warning(f"Высокая нагрузка на сервере {server.name}: {metric}")
        
        # Создаем запись в журнале
        from models import ServerLog
        from app import db
        log = ServerLog(
            server_id=server.id,
            action="high_load",
            status="warning",
            message=f"Высокая нагрузка на сервере: {metric}"
        )
        db.session.add(log)
        db.session.commit()
        
        # Маскируем IP-адрес для уведомления
        masked_ip = self._mask_ip_address(server.ip_address)
        
        # Отправляем уведомление в Telegram
        TelegramNotifier.send_alert(
            f"⚠️ Высокая нагрузка на сервере {server.name} ({masked_ip})!\n"
            f"Метрика: {metric}"
        )
    
    def _check_external_servers(self):
        """
        Проверяет доступность всех активных внешних серверов и собирает их метрики.
        """
        try:
            logger.info("Запуск проверки внешних серверов")
            
            # Используем GlancesManager для проверки всех внешних серверов
            result = GlancesManager.check_all_external_servers()
            
            logger.info(f"Проверка внешних серверов завершена. Результаты: {result}")
        except Exception as e:
            logger.error(f"Ошибка при проверке внешних серверов: {str(e)}")
            

# Создаем экземпляр класса для управления фоновыми задачами
background_tasks = BackgroundTasks()