import logging
import re
from datetime import datetime, timedelta
from sqlalchemy import func

from models import db, Server, Domain, ServerMetric, DomainMetric
from modules.server_manager import ServerManager

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
        
        Args:
            server: Server model instance
            
        Returns:
            ServerMetric: The created metric object or None if collection fails
        """
        if not server or server.status != 'active':
            logger.warning(f"Cannot collect metrics for inactive server {server.name if server else 'unknown'}")
            return None
        
        try:
            # Check connectivity
            if not ServerManager.check_connectivity(server):
                logger.warning(f"Server {server.name} is not reachable, skipping metrics collection")
                return None
            
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
            
            logger.info(f"Collected server metrics for {server.name}: CPU {cpu_usage}%, Memory {memory_usage}%, Disk {disk_usage}%")
            return metric
            
        except Exception as e:
            logger.exception(f"Error collecting server metrics for {server.name}: {str(e)}")
            db.session.rollback()
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
                f"/var/log/nginx/{domain_name}.access.log",
                f"/var/log/nginx/access.{domain_name}.log",
                f"/var/log/nginx/{domain_name}_access.log",
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
            since_str = since.strftime("%Y:%H:%M:%S")
            
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
                    avg_response_time=None,
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
                    # Есть какие-то логи, но не за последний час
                    logger.info(f"No requests in the last hour for {domain.name}, but log has {total_lines} entries")
                else:
                    logger.info(f"Log file exists but is empty for {domain.name}")
                
                bandwidth_used = 0
                avg_response_time = None
            else:
                # Get bandwidth used (sum of response sizes)
                stdout, _ = ServerManager.execute_command(
                    server,
                    f"grep '{since_str}' {log_path} | awk '{{sum+=$10}} END {{print sum}}'"
                )
                bandwidth_used = int(stdout.strip()) if stdout.strip().isdigit() else 0
                
                # Get response time average (if using Nginx's $request_time variable)
                stdout, _ = ServerManager.execute_command(
                    server,
                    f"grep '{since_str}' {log_path} | awk '{{sum+=$11; count+=1}} END {{if(count>0) print sum/count*1000; else print 0}}'"
                )
            avg_response_time = float(stdout.strip()) if stdout.strip() and re.match(r'^[0-9.]+$', stdout.strip()) else None
            
            # Get status code counts
            stdout, _ = ServerManager.execute_command(
                server,
                f"grep '{since_str}' {log_path} | cut -d ' ' -f 9 | sort | uniq -c"
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