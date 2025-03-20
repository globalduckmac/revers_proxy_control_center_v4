import logging
import time
import threading
from datetime import datetime, timedelta

from app import db
from models import Server, Domain
from modules.server_manager import ServerManager
from modules.domain_manager import DomainManager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Интервалы выполнения задач (в секундах)
CHECK_SERVER_INTERVAL = 300  # 5 минут
CHECK_DOMAIN_NS_INTERVAL = 300  # 5 минут

class BackgroundTasks:
    """
    Класс для управления фоновыми задачами в системе.
    """
    def __init__(self):
        self.is_running = False
        self.threads = []
    
    def start(self):
        """Запускает все фоновые задачи."""
        if self.is_running:
            logger.warning("Background tasks are already running")
            return
        
        self.is_running = True
        
        # Запускаем задачу проверки серверов
        server_check_thread = threading.Thread(
            target=self._run_task,
            args=(self._check_servers, CHECK_SERVER_INTERVAL, "Server check"),
            daemon=True
        )
        self.threads.append(server_check_thread)
        server_check_thread.start()
        
        # Запускаем задачу проверки NS-записей доменов
        domain_ns_check_thread = threading.Thread(
            target=self._run_task,
            args=(self._check_domains_ns, CHECK_DOMAIN_NS_INTERVAL, "Domain NS check"),
            daemon=True
        )
        self.threads.append(domain_ns_check_thread)
        domain_ns_check_thread.start()
        
        logger.info("Background tasks started")
    
    def stop(self):
        """Останавливает все фоновые задачи."""
        self.is_running = False
        logger.info("Background tasks stopped")
    
    def _run_task(self, task_func, interval, task_name):
        """
        Запускает задачу с указанным интервалом.
        
        Args:
            task_func: Функция для выполнения
            interval: Интервал между выполнениями в секундах
            task_name: Имя задачи для логирования
        """
        logger.info(f"Starting {task_name} task, interval: {interval} seconds")
        
        while self.is_running:
            try:
                # Выполняем задачу
                logger.info(f"Running {task_name} task")
                task_func()
                
                # Устанавливаем следующее время выполнения
                logger.info(f"{task_name} task completed, next run in {interval} seconds")
                
                # Ждем до следующего запуска
                for _ in range(interval):
                    if not self.is_running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in {task_name} task: {str(e)}")
                time.sleep(60)  # В случае ошибки ждем минуту перед повторной попыткой
    
    def _check_servers(self):
        """Проверяет доступность всех серверов по SSH."""
        from app import app
        with app.app_context():
            servers = Server.query.all()
            
            for server in servers:
                try:
                    # Проверяем соединение
                    is_reachable = ServerManager.check_connectivity(server)
                    
                    # Обновляем статус
                    old_status = server.status
                    server.status = 'active' if is_reachable else 'error'
                    server.last_check = datetime.utcnow()
                    
                    # Если статус изменился, добавляем запись в лог
                    if old_status != server.status:
                        from models import ServerLog
                        log = ServerLog(
                            server_id=server.id,
                            action='connectivity_check',
                            status='success' if is_reachable else 'error',
                            message=f"Server status changed from {old_status} to {server.status}"
                        )
                        db.session.add(log)
                    
                    db.session.commit()
                    
                except Exception as e:
                    logger.error(f"Error checking server {server.name}: {str(e)}")
                    db.session.rollback()
    
    def _check_domains_ns(self):
        """Проверяет NS-записи всех доменов, для которых указаны ожидаемые значения."""
        from app import app
        with app.app_context():
            try:
                # Получаем все домены с указанными ожидаемыми NS
                domains = Domain.query.filter(Domain.expected_nameservers.isnot(None)).all()
                
                for domain in domains:
                    try:
                        # Проверяем NS-записи
                        DomainManager.check_domain_ns_status(domain.id)
                    except Exception as e:
                        logger.error(f"Error checking NS for domain {domain.name}: {str(e)}")
                
            except Exception as e:
                logger.error(f"Error in domain NS check task: {str(e)}")
                db.session.rollback()

# Создаем глобальный экземпляр менеджера задач
background_tasks = BackgroundTasks()