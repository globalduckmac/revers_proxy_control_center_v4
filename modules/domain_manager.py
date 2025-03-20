import logging
import dns.resolver
from datetime import datetime
from models import Domain, DomainGroup, Server, ServerLog, db

logger = logging.getLogger(__name__)

class DomainManager:
    """
    Handles operations related to domain and domain group management.
    """
    
    @staticmethod
    def check_nameservers(domain_name):
        """
        Получает список актуальных NS-записей для домена
        
        Args:
            domain_name: Имя домена для проверки
            
        Returns:
            list: Список NS-записей
        """
        try:
            answers = dns.resolver.resolve(domain_name, 'NS')
            nameservers = [ns.target.to_text().rstrip('.').lower() for ns in answers]
            return nameservers
        except Exception as e:
            logger.error(f"Error checking nameservers for {domain_name}: {str(e)}")
            return []
            
    @staticmethod
    def check_domain_ns_status(domain_id):
        """
        Проверяет соответствие NS-записей домена с ожидаемыми значениями
        
        Args:
            domain_id: ID домена для проверки
            
        Returns:
            bool: True если проверка пройдена, False в случае ошибки или несоответствия
        """
        try:
            domain = Domain.query.get(domain_id)
            if not domain:
                logger.error(f"Domain with ID {domain_id} not found")
                return False
                
            # Если ожидаемые NS не указаны, пропускаем проверку
            if not domain.expected_nameservers:
                domain.ns_status = 'pending'
                db.session.commit()
                return True
                
            # Получаем текущие NS записи
            actual_ns = DomainManager.check_nameservers(domain.name)
            
            # Записываем в базу актуальные NS
            domain.actual_nameservers = ','.join(actual_ns)
            domain.ns_check_date = datetime.utcnow()
            
            # Разбираем ожидаемые NS
            expected_ns = [ns.strip().lower() for ns in domain.expected_nameservers.split(',')]
            
            # Сравниваем списки
            if set(actual_ns) == set(expected_ns):
                domain.ns_status = 'ok'
                logger.info(f"Domain {domain.name} NS check: OK")
            else:
                domain.ns_status = 'mismatch'
                logger.warning(f"Domain {domain.name} NS mismatch. Expected: {expected_ns}, Actual: {actual_ns}")
                
            db.session.commit()
            return domain.ns_status == 'ok'
            
        except Exception as e:
            logger.error(f"Error checking NS status for domain {domain_id}: {str(e)}")
            return False
            
    @staticmethod
    def update_expected_nameservers(domain_id, expected_nameservers):
        """
        Обновляет список ожидаемых NS-записей для домена
        
        Args:
            domain_id: ID домена
            expected_nameservers: Список ожидаемых NS-серверов (строка, разделенная запятыми)
            
        Returns:
            bool: True если обновление успешно, False в случае ошибки
        """
        try:
            domain = Domain.query.get(domain_id)
            if not domain:
                logger.error(f"Domain with ID {domain_id} not found")
                return False
                
            domain.expected_nameservers = expected_nameservers
            domain.ns_status = 'pending'  # Сбрасываем статус для следующей проверки
            db.session.commit()
            
            logger.info(f"Updated expected nameservers for domain {domain.name}: {expected_nameservers}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating nameservers for domain {domain_id}: {str(e)}")
            return False
            
    @staticmethod
    def check_all_domains_ns_status():
        """
        Проверяет NS-статус для всех доменов, у которых указаны ожидаемые NS
        
        Returns:
            dict: Словарь с результатами проверки: {'ok': count, 'mismatch': count, 'error': count}
        """
        results = {'ok': 0, 'mismatch': 0, 'error': 0}
        
        try:
            # Получаем все домены с указанными ожидаемыми NS
            domains = Domain.query.filter(Domain.expected_nameservers.isnot(None)).all()
            
            for domain in domains:
                try:
                    if DomainManager.check_domain_ns_status(domain.id):
                        results['ok'] += 1
                    else:
                        if domain.ns_status == 'mismatch':
                            results['mismatch'] += 1
                        else:
                            results['error'] += 1
                except Exception as e:
                    logger.error(f"Error checking domain {domain.name}: {str(e)}")
                    results['error'] += 1
                    
            logger.info(f"Checked NS status for {len(domains)} domains. Results: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Error in bulk NS check: {str(e)}")
            return results
    
    @staticmethod
    def get_domains_by_group(group_id):
        """
        Get all domains associated with a domain group.
        
        Args:
            group_id: ID of the domain group
            
        Returns:
            list: List of Domain objects
        """
        try:
            group = DomainGroup.query.get(group_id)
            if not group:
                logger.error(f"Domain group with ID {group_id} not found")
                return []
                
            return group.domains.all()
        except Exception as e:
            logger.error(f"Error retrieving domains for group {group_id}: {str(e)}")
            return []
    
    @staticmethod
    def get_domains_by_server(server_id):
        """
        Get all domains associated with a server through domain groups.
        
        Args:
            server_id: ID of the server
            
        Returns:
            list: List of Domain objects
        """
        try:
            # Find all domain groups associated with the server
            domain_groups = DomainGroup.query.filter_by(server_id=server_id).all()
            
            # Collect all domains from these groups
            domains = []
            for group in domain_groups:
                domains.extend(group.domains.all())
                
            # Remove duplicates (a domain could be in multiple groups)
            unique_domains = list({domain.id: domain for domain in domains}.values())
            
            return unique_domains
        except Exception as e:
            logger.error(f"Error retrieving domains for server {server_id}: {str(e)}")
            return []
    
    @staticmethod
    def create_domain(name, target_ip, target_port=80, ssl_enabled=False):
        """
        Create a new domain.
        
        Args:
            name: Domain name (e.g., example.com)
            target_ip: Target IP address for proxying
            target_port: Target port (default: 80)
            ssl_enabled: Whether SSL should be enabled
            
        Returns:
            Domain: Created domain object or None if creation fails
        """
        try:
            # Check if domain already exists
            existing_domain = Domain.query.filter_by(name=name).first()
            if existing_domain:
                logger.warning(f"Domain {name} already exists")
                return None
                
            # Create new domain
            domain = Domain(
                name=name,
                target_ip=target_ip,
                target_port=target_port,
                ssl_enabled=ssl_enabled
            )
            
            db.session.add(domain)
            db.session.commit()
            
            logger.info(f"Created domain {name} pointing to {target_ip}:{target_port}")
            return domain
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating domain {name}: {str(e)}")
            return None
    
    @staticmethod
    def add_domain_to_group(domain_id, group_id):
        """
        Add a domain to a domain group.
        
        Args:
            domain_id: ID of the domain to add
            group_id: ID of the group to add the domain to
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            domain = Domain.query.get(domain_id)
            if not domain:
                logger.error(f"Domain with ID {domain_id} not found")
                return False
                
            group = DomainGroup.query.get(group_id)
            if not group:
                logger.error(f"Domain group with ID {group_id} not found")
                return False
                
            # Check if domain is already in the group
            if domain in group.domains:
                logger.warning(f"Domain {domain.name} is already in group {group.name}")
                return True
                
            # Add domain to group
            group.domains.append(domain)
            db.session.commit()
            
            logger.info(f"Added domain {domain.name} to group {group.name}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding domain {domain_id} to group {group_id}: {str(e)}")
            return False
    
    @staticmethod
    def remove_domain_from_group(domain_id, group_id):
        """
        Remove a domain from a domain group.
        
        Args:
            domain_id: ID of the domain to remove
            group_id: ID of the group to remove the domain from
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            domain = Domain.query.get(domain_id)
            if not domain:
                logger.error(f"Domain with ID {domain_id} not found")
                return False
                
            group = DomainGroup.query.get(group_id)
            if not group:
                logger.error(f"Domain group with ID {group_id} not found")
                return False
                
            # Check if domain is in the group
            if domain not in group.domains:
                logger.warning(f"Domain {domain.name} is not in group {group.name}")
                return True
                
            # Remove domain from group
            group.domains.remove(domain)
            db.session.commit()
            
            logger.info(f"Removed domain {domain.name} from group {group.name}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing domain {domain_id} from group {group_id}: {str(e)}")
            return False
    
    @staticmethod
    def create_domain_group(name, server_id=None):
        """
        Create a new domain group.
        
        Args:
            name: Group name
            server_id: Optional ID of the server to associate with (can be None)
            
        Returns:
            DomainGroup: Created group object or None if creation fails
        """
        try:
            # Check if server exists if server_id is provided
            if server_id:
                server = Server.query.get(server_id)
                if not server:
                    logger.error(f"Server with ID {server_id} not found")
                    return None
            
            # Create new domain group
            group = DomainGroup(
                name=name,
                server_id=server_id
            )
            
            db.session.add(group)
            db.session.commit()
            
            if server_id:
                logger.info(f"Created domain group {name} associated with server ID {server_id}")
            else:
                logger.info(f"Created domain group {name} (not associated with any server)")
                
            return group
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating domain group {name}: {str(e)}")
            return None
    
    @staticmethod
    def assign_group_to_server(group_id, server_id):
        """
        Assign a domain group to a server.
        
        Args:
            group_id: ID of the domain group
            server_id: ID of the server
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            group = DomainGroup.query.get(group_id)
            if not group:
                logger.error(f"Domain group with ID {group_id} not found")
                return False
                
            server = Server.query.get(server_id)
            if not server:
                logger.error(f"Server with ID {server_id} not found")
                return False
                
            # Update group's server
            group.server_id = server_id
            db.session.commit()
            
            # Create server log entry
            log = ServerLog(
                server_id=server_id,
                action='domain_group_assignment',
                status='success',
                message=f"Domain group '{group.name}' (ID: {group_id}) assigned to server"
            )
            
            db.session.add(log)
            db.session.commit()
            
            logger.info(f"Assigned domain group {group.name} to server {server.name}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error assigning group {group_id} to server {server_id}: {str(e)}")
            return False
