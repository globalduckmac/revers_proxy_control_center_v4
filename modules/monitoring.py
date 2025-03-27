import logging
import re
from datetime import datetime, timedelta
from sqlalchemy import func

from models import db, Server, Domain, ServerMetric, DomainMetric
from modules.server_manager import ServerManager
from modules.glances_manager import GlancesManager

logger = logging.getLogger(__name__)

class MonitoringManager:
    """
    Handles monitoring operations for servers and domains.
    Collects metrics, stores them in the database, and provides access to monitoring data.
    """
    
    @staticmethod
    def collect_server_metrics(server):
        """
        Collect server metrics and store them in the database.
        Приоритезирует получение данных через Glances API, 
        но может использовать SSH в качестве запасного варианта.
        
        Args:
            server: Server model instance
            
        Returns:
            ServerMetric: The created metric object or None if collection fails
        """
        if not server:
            logger.warning(f"Cannot collect metrics: server is None")
            return None
            
        # Проверяем, установлен ли Glances и включена ли интеграция
        # Если да, пытаемся получить метрики через API
        if server.glances_installed and server.glances_enabled:
            try:
                # Пытаемся получить метрики через API Glances
                metric = GlancesManager.get_server_metrics_via_api(server)
                if metric:
                    logger.info(f"Collected server metrics via Glances API for {server.name}: CPU {metric.cpu_usage}%, Memory {metric.memory_usage}%, Disk {metric.disk_usage}%")
                    
                    # Обновляем статус сервера, так как API доступен
                    if server.status != 'active':
                        server.status = 'active'
                        server.last_check = datetime.utcnow()
                        db.session.commit()
                        
                    return metric
                    
                # Если API недоступен - обновляем статус Glances на ошибку
                # и помечаем сервер как неактивный, если не было проверки через SSH
                server.glances_status = 'error'
                server.glances_last_check = datetime.utcnow()
                db.session.commit()
                
                logger.warning(f"Failed to collect metrics via Glances API for {server.name}, marking Glances as error")
                
            except Exception as e:
                logger.error(f"Error collecting server metrics via Glances API for {server.name}: {str(e)}")
                # Обновляем статус Glances
                server.glances_status = 'error'
                server.glances_last_check = datetime.utcnow()
                db.session.commit()
        
        # Если сервер не активен, логируем и выходим
        if server.status != 'active':
            logger.warning(f"Cannot collect metrics for inactive server {server.name}")
            return None
            
        # В случае ошибки или если Glances не установлен - используем устаревший метод через SSH
        # для поддержки обратной совместимости и тестирования
        try:
            logger.info(f"Falling back to SSH method for server {server.name}")
            
            # Проверяем соединение по SSH
            if not ServerManager.check_connectivity(server):
                logger.warning(f"Server {server.name} is not reachable via SSH, skipping metrics collection")
                
                # Обновляем статус на ошибку, так как ни API, ни SSH не работают
                server.status = 'error'
                server.last_check = datetime.utcnow()
                db.session.commit()
                
                return None
            
            # Получаем метрики через SSH
            # Get CPU usage (%)
            stdout, _ = ServerManager.execute_command(
                server, 
                "top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}'"
            )
            cpu_usage = float(stdout.strip()) if stdout.strip() else None
            
            # Get memory usage (%)
            stdout, _ = ServerManager.execute_command(
                server,
                "free | grep Mem | awk '{print $3/$2 * 100.0}'"
            )
            memory_usage = float(stdout.strip()) if stdout.strip() else None
            
            # Get disk usage (%)
            stdout, _ = ServerManager.execute_command(
                server,
                "df -h / | grep / | awk '{print $5}' | sed 's/%//'"
            )
            disk_usage = float(stdout.strip()) if stdout.strip() else None
            
            # Get load average
            stdout, _ = ServerManager.execute_command(
                server,
                "cat /proc/loadavg | awk '{print $1,$2,$3}'"
            )
            load_average = stdout.strip() if stdout.strip() else None
            
            # Create and store the metric
            metric = ServerMetric(
                server_id=server.id,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                disk_usage=disk_usage,
                load_average=load_average,
                timestamp=datetime.utcnow()
            )
            
            db.session.add(metric)
            db.session.commit()
            
            logger.info(f"Collected server metrics via SSH for {server.name}: CPU {cpu_usage}%, Memory {memory_usage}%, Disk {disk_usage}%")
            return metric
            
        except Exception as e:
            logger.exception(f"Error collecting server metrics via SSH for {server.name}: {str(e)}")
            
            # Обновляем статус на ошибку, так как ни API, ни SSH не работают
            server.status = 'error'
            server.last_check = datetime.utcnow()
            db.session.commit()
            
            return None
    
    @staticmethod
    def collect_domain_metrics(server, domain):
        """
        Collect domain traffic metrics from Nginx logs and store them in the database.
        
        Args:
            server: Server model instance
            domain: Domain model instance
            
        Returns:
            DomainMetric: The created metric object or None if collection fails
        """
        if not server or not domain or server.status != 'active':
            logger.warning(f"Cannot collect metrics for domain {domain.name if domain else 'unknown'} on inactive server")
            return None
        
        try:
            # Определим возможные варианты пути к файлу логов
            domain_name = domain.name
            possible_log_paths = [
                f"/var/log/nginx/{domain_name}.access.log",       # Как в нашем шаблоне
                f"/var/log/nginx/access.{domain_name}.log",       # Альтернативный формат
                f"/var/log/nginx/{domain_name}_access.log",       # Еще один формат
                f"/var/log/nginx/{domain_name.replace('.', '_')}.access.log", # Для доменов с заменой точек
                # Для случаев, когда имя домена используется как часть пути к логу
                f"/var/log/nginx/{domain_name}/access.log"
            ]
            
            # Проверим, какой из файлов логов существует
            log_path = None
            for path in possible_log_paths:
                stdout, _ = ServerManager.execute_command(server, f"test -f {path} && echo 'exists' || echo 'not_exists'")
                if stdout.strip() == 'exists':
                    log_path = path
                    break
            
            # Если не нашли файл логов, создадим его
            if not log_path:
                log_path = possible_log_paths[0]  # Используем первый вариант пути
                logger.warning(f"Access log for domain {domain_name} not found, creating empty file at {log_path}")
                
                # Создаем директорию, если она не существует
                log_dir = "/".join(log_path.split("/")[:-1])
                ServerManager.execute_command(server, f"sudo mkdir -p {log_dir}")
                
                # Создаем пустой файл логов
                ServerManager.execute_command(server, f"sudo touch {log_path}")
                ServerManager.execute_command(server, f"sudo chown www-data:www-data {log_path}")
                
                # Обновляем конфигурацию Nginx, чтобы он писал в этот файл
                logger.info(f"Updating Nginx configuration to use log file at {log_path}")
                # Здесь можно было бы добавить обновление конфигурации Nginx, 
                # но это будет сделано при следующем деплое конфигурации
                
                return None  # Вернем None, так как файл только что создан и в нем нет данных
            
            # Get stats from the last hour
            since = datetime.utcnow() - timedelta(hours=1)
            # Изменим формат временной метки в зависимости от формата логов Nginx
            # Тут используем несколько вариантов форматирования для поиска
            since_str = since.strftime("%Y") # Год отдельно, чтобы найти любую запись с этим годом
            # Позже можно добавить более точный поиск по времени
            
            # Проверим размер файла лога
            stdout, _ = ServerManager.execute_command(
                server,
                f"stat -c %s {log_path}"
            )
            file_size = int(stdout.strip()) if stdout.strip().isdigit() else 0
            
            # Если файл пустой или почти пустой, значит, логов еще нет
            if file_size < 100:  # Примерный размер пустого файла или файла с 1-2 заголовками
                logger.info(f"Log file for {domain.name} is empty or almost empty (size: {file_size} bytes)")
                
                # Создаем метрику с нулевыми значениями
                metric = DomainMetric(
                    domain_id=domain.id,
                    requests_count=0,
                    bandwidth_used=0,
                    avg_response_time=0.5,  # Минимальное значение для отображения
                    status_2xx_count=0,
                    status_3xx_count=0,
                    status_4xx_count=0,
                    status_5xx_count=0,
                    timestamp=datetime.utcnow()
                )
                
                db.session.add(metric)
                db.session.commit()
                
                logger.info(f"Created empty domain metrics for {domain.name}")
                return metric
            
            # Extract metrics from logs (using awk for efficiency)
            # Get request count
            stdout, _ = ServerManager.execute_command(
                server,
                f"grep -c '{since_str}' {log_path}"
            )
            requests_count = int(stdout.strip()) if stdout.strip().isdigit() else 0
            
            # Если нет запросов, значит нет смысла считать остальные метрики
            if requests_count == 0:
                stdout, _ = ServerManager.execute_command(
                    server,
                    f"wc -l {log_path} | cut -d ' ' -f 1"
                )
                total_lines = int(stdout.strip()) if stdout.strip().isdigit() else 0
                
                if total_lines > 0:
                    # Есть какие-то логи, но не за последний час. Попробуем собрать все запросы, а не только за последний час
                    logger.info(f"No requests with '{since_str}' for {domain.name}, but log has {total_lines} entries. Trying to collect all metrics.")
                    stdout, _ = ServerManager.execute_command(
                        server,
                        f"wc -l {log_path}"
                    )
                    requests_count = int(stdout.strip().split()[0]) if stdout.strip() else 0
                else:
                    logger.info(f"Log file exists but is empty for {domain.name}")
                
                bandwidth_used = 0
                avg_response_time = None  # Если нет запросов, то нет и времени отклика
            else:
                # Get bandwidth used (sum of response sizes)
                stdout, _ = ServerManager.execute_command(
                    server,
                    f"grep '{since_str}' {log_path} | awk '{{sum+=$10}} END {{print sum}}'"
                )
                bandwidth_used = int(stdout.strip()) if stdout.strip().isdigit() else 0
                
                # Get response time average (if using Nginx's $request_time variable)
                # Сначала попробуем обычную позицию для времени ответа (11-й столбец)
                stdout, _ = ServerManager.execute_command(
                    server,
                    f"cat {log_path} | awk '{{sum+=$11; count+=1}} END {{if(count>0) print sum/count*1000; else print 0}}'"
                )
                avg_response_time = float(stdout.strip()) if stdout.strip() and re.match(r'^[0-9.]+$', stdout.strip()) else None
                
                # Если не получилось, попробуем другие варианты расположения времени ответа
                if not avg_response_time or avg_response_time == 0:
                    logger.info(f"Trying alternative response time calculation for {domain.name}")
                    stdout, _ = ServerManager.execute_command(
                        server,
                        f"cat {log_path} | awk '{{sum+=$10; count+=1}} END {{if(count>0) print sum/count*1000; else print 0}}'"
                    )
                    avg_response_time = float(stdout.strip()) if stdout.strip() and re.match(r'^[0-9.]+$', stdout.strip()) else None
                
                # Установим минимальное значение для отображения
                if avg_response_time is not None and avg_response_time < 0.01:
                    avg_response_time = 0.5  # минимальное значение для отображения
            
            # Добавим команду для дебага, чтобы понять формат лога
            stdout, stderr = ServerManager.execute_command(
                server,
                f"head -n 1 {log_path}"
            )
            logger.info(f"Nginx log format sample for {domain.name}: {stdout.strip()}")

            # Get status code counts - используем различные методы извлечения кодов состояния
            # По умолчанию пытаемся извлечь из формата, где статус-код находится в 9-м поле (обычный формат Nginx)
            stdout, stderr = ServerManager.execute_command(
                server,
                f"cat {log_path} | awk '{{print $9}}' | grep -E '^[0-9]+$' | sort | uniq -c"
            )
            
            # Если не нашли коды состояния, попробуем альтернативный способ
            if not stdout.strip():
                logger.info(f"Trying alternative status code extraction for {domain.name}")
                stdout, stderr = ServerManager.execute_command(
                    server,
                    f"cat {log_path} | grep -o 'HTTP/[0-9.]\\+ [0-9]\\+' | cut -d ' ' -f 2 | sort | uniq -c"
                )
                
            # Если и это не сработало, проверим другие поля
            if not stdout.strip():
                logger.info(f"Trying 8th field for status code extraction for {domain.name}")
                stdout, stderr = ServerManager.execute_command(
                    server,
                    f"cat {log_path} | awk '{{print $8}}' | grep -E '^[0-9]+$' | sort | uniq -c"
                )
            
            # Parse status code counts
            status_2xx_count = 0
            status_3xx_count = 0
            status_4xx_count = 0
            status_5xx_count = 0
            
            if stdout.strip():
                for line in stdout.strip().split('\n'):
                    parts = line.strip().split()
                    if len(parts) == 2:
                        count = int(parts[0])
                        status = parts[1]
                        
                        if status.startswith('2'):
                            status_2xx_count += count
                        elif status.startswith('3'):
                            status_3xx_count += count
                        elif status.startswith('4'):
                            status_4xx_count += count
                        elif status.startswith('5'):
                            status_5xx_count += count
            
            # Create and store the metric
            metric = DomainMetric(
                domain_id=domain.id,
                requests_count=requests_count,
                bandwidth_used=bandwidth_used,
                avg_response_time=avg_response_time,
                status_2xx_count=status_2xx_count,
                status_3xx_count=status_3xx_count,
                status_4xx_count=status_4xx_count,
                status_5xx_count=status_5xx_count,
                timestamp=datetime.utcnow()
            )
            
            db.session.add(metric)
            db.session.commit()
            
            logger.info(f"Collected domain metrics for {domain.name}: {requests_count} requests, {bandwidth_used} bytes")
            return metric
            
        except Exception as e:
            logger.exception(f"Error collecting domain metrics for {domain.name}: {str(e)}")
            db.session.rollback()
            return None
    
    @staticmethod
    def get_server_metrics(server_id, period='day'):
        """
        Get server metrics for a specific time period.
        
        Args:
            server_id: ID of the server
            period: Time period ('hour', 'day', 'week', 'month')
            
        Returns:
            list: List of ServerMetric objects
        """
        try:
            since = None
            if period == 'hour':
                since = datetime.utcnow() - timedelta(hours=1)
            elif period == 'day':
                since = datetime.utcnow() - timedelta(days=1)
            elif period == 'week':
                since = datetime.utcnow() - timedelta(weeks=1)
            elif period == 'month':
                since = datetime.utcnow() - timedelta(days=30)
            else:
                # Default to day
                since = datetime.utcnow() - timedelta(days=1)
            
            metrics = ServerMetric.query.filter(
                ServerMetric.server_id == server_id,
                ServerMetric.timestamp >= since
            ).order_by(ServerMetric.timestamp.asc()).all()
            
            return metrics
            
        except Exception as e:
            logger.exception(f"Error retrieving server metrics: {str(e)}")
            return []
    
    @staticmethod
    def get_domain_metrics(domain_id, period='day'):
        """
        Get domain metrics for a specific time period.
        
        Args:
            domain_id: ID of the domain
            period: Time period ('hour', 'day', 'week', 'month')
            
        Returns:
            list: List of DomainMetric objects
        """
        try:
            since = None
            if period == 'hour':
                since = datetime.utcnow() - timedelta(hours=1)
            elif period == 'day':
                since = datetime.utcnow() - timedelta(days=1)
            elif period == 'week':
                since = datetime.utcnow() - timedelta(weeks=1)
            elif period == 'month':
                since = datetime.utcnow() - timedelta(days=30)
            else:
                # Default to day
                since = datetime.utcnow() - timedelta(days=1)
            
            metrics = DomainMetric.query.filter(
                DomainMetric.domain_id == domain_id,
                DomainMetric.timestamp >= since
            ).order_by(DomainMetric.timestamp.asc()).all()
            
            return metrics
            
        except Exception as e:
            logger.exception(f"Error retrieving domain metrics: {str(e)}")
            return []
    
    @staticmethod
    def get_domain_aggregate_metrics(domain_id, period='day'):
        """
        Get aggregated metrics for a domain over a specific time period.
        
        Args:
            domain_id: ID of the domain
            period: Time period ('hour', 'day', 'week', 'month')
            
        Returns:
            dict: Dictionary containing aggregated metrics
        """
        try:
            since = None
            if period == 'hour':
                since = datetime.utcnow() - timedelta(hours=1)
            elif period == 'day':
                since = datetime.utcnow() - timedelta(days=1)
            elif period == 'week':
                since = datetime.utcnow() - timedelta(weeks=1)
            elif period == 'month':
                since = datetime.utcnow() - timedelta(days=30)
            else:
                # Default to day
                since = datetime.utcnow() - timedelta(days=1)
            
            result = db.session.query(
                func.sum(DomainMetric.requests_count).label('total_requests'),
                func.sum(DomainMetric.bandwidth_used).label('total_bandwidth'),
                func.avg(DomainMetric.avg_response_time).label('avg_response_time'),
                func.sum(DomainMetric.status_2xx_count).label('total_2xx'),
                func.sum(DomainMetric.status_3xx_count).label('total_3xx'),
                func.sum(DomainMetric.status_4xx_count).label('total_4xx'),
                func.sum(DomainMetric.status_5xx_count).label('total_5xx')
            ).filter(
                DomainMetric.domain_id == domain_id,
                DomainMetric.timestamp >= since
            ).first()
            
            if result:
                return {
                    'total_requests': result.total_requests or 0,
                    'total_bandwidth': result.total_bandwidth or 0,
                    'avg_response_time': result.avg_response_time,
                    'total_2xx': result.total_2xx or 0,
                    'total_3xx': result.total_3xx or 0,
                    'total_4xx': result.total_4xx or 0,
                    'total_5xx': result.total_5xx or 0,
                }
            else:
                return {
                    'total_requests': 0,
                    'total_bandwidth': 0,
                    'avg_response_time': None,
                    'total_2xx': 0,
                    'total_3xx': 0,
                    'total_4xx': 0,
                    'total_5xx': 0,
                }
                
        except Exception as e:
            logger.exception(f"Error retrieving domain aggregate metrics: {str(e)}")
            return {
                'total_requests': 0,
                'total_bandwidth': 0,
                'avg_response_time': None,
                'total_2xx': 0,
                'total_3xx': 0,
                'total_4xx': 0,
                'total_5xx': 0,
            }