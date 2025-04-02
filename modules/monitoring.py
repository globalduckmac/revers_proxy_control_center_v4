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
        Получает данные только через Glances API.
        
        Args:
            server: Server model instance
            
        Returns:
            ServerMetric: The created metric object or None if collection fails
        """
        if not server:
            logger.warning(f"Cannot collect metrics: server is None")
            return None
            
        # Проверяем, установлен ли Glances и включена ли интеграция
        if not server.glances_installed or not server.glances_enabled:
            logger.warning(f"Cannot collect metrics for server {server.name}: Glances not installed or disabled")
            return None
            
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
            server.glances_status = 'error'
            server.glances_last_check = datetime.utcnow()
            db.session.commit()
            
            logger.warning(f"Failed to collect metrics via Glances API for {server.name}, marking Glances as error")
            return None
                
        except Exception as e:
            logger.error(f"Error collecting server metrics via Glances API for {server.name}: {str(e)}")
            # Обновляем статус Glances
            server.glances_status = 'error'
            server.glances_last_check = datetime.utcnow()
            db.session.commit()
            
            return None
    
    @staticmethod
    def collect_domain_metrics(server, domain):
        """
        Collect domain traffic metrics feature has been removed.
        Domain metrics collection via SSH has been disabled in this version.
        
        Args:
            server: Server model instance
            domain: Domain model instance
            
        Returns:
            None: Always returns None as this functionality is disabled
        """
        logger.warning(f"Domain metrics collection via SSH has been disabled in this version. Cannot collect metrics for {domain.name if domain else 'unknown'}")
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