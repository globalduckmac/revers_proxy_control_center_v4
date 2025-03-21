import logging
import dns.resolver
from datetime import datetime
from models import Domain, DomainGroup, Server, ServerLog, db
from modules.ffpanel_api import FFPanelAPI

logger = logging.getLogger(__name__)

class DomainManager:
    """
    Handles operations related to domain and domain group management.
    """
    
    @staticmethod
    def check_nameservers(domain_name, max_attempts=3, retry_delay=5):
        """
        Получает список актуальных NS-записей для домена
        Делает несколько попыток при возникновении ошибок для более надежной проверки.
        
        Args:
            domain_name: Имя домена для проверки
            max_attempts: Максимальное количество попыток (по умолчанию 3)
            retry_delay: Задержка между попытками в секундах (по умолчанию 5)
            
        Returns:
            list: Список NS-записей
        """
        import time
        
        for attempt in range(1, max_attempts + 1):
            try:
                # Используем публичный DNS-сервер Google для надежности
                resolver = dns.resolver.Resolver()
                resolver.nameservers = ['8.8.8.8', '8.8.4.4']
                resolver.timeout = 10  # Увеличиваем таймаут до 10 секунд для более стабильной проверки
                
                # Запрашиваем NS-записи
                answers = resolver.resolve(domain_name, 'NS')
                nameservers = [ns.target.to_text().rstrip('.').lower() for ns in answers]
                
                # Если успешно получили результат, возвращаем его
                logger.info(f"Successfully retrieved NS records for {domain_name} on attempt {attempt}: {nameservers}")
                return nameservers
                
            except Exception as e:
                # Маскируем имя домена в сообщениях об ошибках для безопасности
                from modules.telegram_notifier import mask_domain_name
                masked_domain_name = mask_domain_name(domain_name)
                error_msg = f"Error checking nameservers for domain {masked_domain_name} (attempt {attempt}/{max_attempts}): {str(e)}"
                
                if attempt < max_attempts:
                    logger.warning(f"{error_msg}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    # Это была последняя попытка
                    logger.error(f"{error_msg}. Giving up after {max_attempts} attempts.")
        
        # Если все попытки завершились ошибкой, возвращаем пустой список
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
                
            # Для безопасности логирования сразу получаем маскированное имя
            from modules.telegram_notifier import mask_domain_name
            masked_domain_name = mask_domain_name(domain.name)
                
            # Если ожидаемые NS не указаны, пропускаем проверку
            if not domain.expected_nameservers:
                domain.ns_status = 'pending'
                try:
                    db.session.commit()
                except Exception as db_error:
                    logger.error(f"Database error when updating domain {masked_domain_name} status to pending: {str(db_error)}")
                    db.session.rollback()
                    raise
                return True
                
            # Получаем текущие NS записи
            actual_ns = DomainManager.check_nameservers(domain.name)
            
            # Записываем в базу актуальные NS
            domain.actual_nameservers = ','.join(actual_ns)
            domain.ns_check_date = datetime.utcnow()
            
            # Разбираем ожидаемые NS
            expected_ns = [ns.strip().lower() for ns in domain.expected_nameservers.split(',')]
            
            # Проверяем, что все ожидаемые NS-серверы присутствуют в фактическом списке
            actual_ns_lowercase = [ns.lower() for ns in actual_ns]
            expected_ns_lowercase = [ns.lower() for ns in expected_ns]
            
            # Обрабатываем особые случаи - проверка на содержание подстроки в NS-серверах
            # Например, "dnspod" должен матчиться с "a.dnspod.com", "b.dnspod.com", и т.д.
            is_special_match = False
            if len(expected_ns_lowercase) == 1:
                special_provider = expected_ns_lowercase[0]
                # Проверяем, что хотя бы один фактический NS содержит ожидаемый провайдер
                is_special_match = any(special_provider in ns for ns in actual_ns_lowercase)
            
            # Стандартная проверка - точное совпадение
            all_expected_found = all(ns in actual_ns_lowercase for ns in expected_ns_lowercase)
            
            if all_expected_found or is_special_match:
                domain.ns_status = 'ok'
                logger.info(f"Domain {masked_domain_name} NS check: OK. All expected NS found in actual NS list.")
            else:
                domain.ns_status = 'mismatch'
                logger.warning(f"Domain {masked_domain_name} NS mismatch. Expected (any of): {expected_ns}, Actual: {actual_ns}")
            
            # Обработка возможных ошибок базы данных
            try:
                db.session.commit()
            except Exception as db_error:
                logger.error(f"Database error updating NS status for domain {masked_domain_name}: {str(db_error)}")
                db.session.rollback()
                raise
                
            return domain.ns_status == 'ok'
            
        except Exception as e:
            logger.error(f"Error checking NS status for domain {domain_id}: {str(e)}")
            try:
                db.session.rollback()  # На всякий случай откатываем транзакцию
            except:
                pass  # Игнорируем ошибки при откате транзакции
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
            
            # Маскируем имя домена в логах для безопасности
            from modules.telegram_notifier import mask_domain_name
            masked_domain_name = mask_domain_name(domain.name)
            logger.info(f"Updated expected nameservers for domain {masked_domain_name}: {expected_nameservers}")
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
        import traceback
        import sys
        import html
        
        results = {'ok': 0, 'mismatch': 0, 'error': 0}
        
        try:
            # Получаем все домены с указанными ожидаемыми NS
            domains = []
            try:
                # Безопасное получение списка доменов с защитой от ошибок кодировки
                domains = Domain.query.filter(Domain.expected_nameservers.isnot(None)).all()
                logger.info(f"Found {len(domains)} domains with expected NS records to check")
            except Exception as db_error:
                error_text = str(db_error)
                # Безопасное логирование ошибки с экранированием специальных символов
                logger.error(f"Database error fetching domains with expected NS: {html.escape(error_text)}")
                logger.error(traceback.format_exc())
                try:
                    db.session.rollback()
                except:
                    logger.error("Failed to rollback session after database error")
                raise
            
            # Проходим по каждому домену и безопасно обрабатываем его
            for domain in domains:
                domain_id = domain.id
                domain_name = ""
                
                try:
                    # Получаем имя домена с защитой от ошибок кодировки
                    domain_name = domain.name if domain.name else ""
                    # Маскируем имя домена в логах для безопасности
                    from modules.telegram_notifier import mask_domain_name
                    masked_domain_name = mask_domain_name(domain_name)
                    
                    # Проверяем домен с дополнительной обработкой ошибок
                    if DomainManager.check_domain_ns_status(domain_id):
                        results['ok'] += 1
                        logger.debug(f"Domain {masked_domain_name} NS check: OK")
                    else:
                        # Получаем обновленный домен после проверки
                        try:
                            updated_domain = Domain.query.get(domain_id)
                            if updated_domain and updated_domain.ns_status == 'mismatch':
                                results['mismatch'] += 1
                                logger.debug(f"Domain {masked_domain_name} NS check: Mismatch")
                            else:
                                results['error'] += 1
                                logger.debug(f"Domain {masked_domain_name} NS check: Error or unknown status")
                        except Exception as db_error:
                            # Безопасное логирование ошибки базы данных
                            error_msg = html.escape(str(db_error))
                            logger.error(f"Database error retrieving updated domain {masked_domain_name}: {error_msg}")
                            try:
                                db.session.rollback()
                            except:
                                logger.error("Failed to rollback session after update error")
                            results['error'] += 1
                except UnicodeEncodeError as unicode_error:
                    # Специальная обработка ошибок кодировки Unicode
                    logger.error(f"Unicode error with domain ID {domain_id}: {html.escape(str(unicode_error))}")
                    results['error'] += 1
                except Exception as e:
                    # Безопасное логирование общих ошибок с экранированием специальных символов
                    error_text = html.escape(str(e))
                    logger.error(f"Error checking domain ID {domain_id}: {error_text}")
                    logger.error(traceback.format_exc())
                    results['error'] += 1
                    try:
                        db.session.rollback()  # Откатываем транзакцию в случае ошибки
                    except:
                        pass  # Игнорируем ошибки при откате транзакции
                
            # Безопасное логирование результатов      
            logger.info(f"Checked NS status for {len(domains)} domains. Results: ok={results['ok']}, mismatch={results['mismatch']}, error={results['error']}")
            return results
            
        except Exception as e:
            # Обработка критических ошибок
            error_text = html.escape(str(e))
            logger.error(f"Critical error in bulk NS check: {error_text}")
            logger.error(traceback.format_exc())
            try:
                db.session.rollback()  # Откатываем транзакцию в случае ошибки
            except:
                logger.error("Failed to rollback session after critical error")
            # Возвращаем безопасный результат
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
                # Маскируем имя домена в логах для безопасности
                from modules.telegram_notifier import mask_domain_name
                masked_domain_name = mask_domain_name(domain.name)
                logger.warning(f"Domain {masked_domain_name} is already in group {group.name}")
                return True
                
            # Add domain to group
            group.domains.append(domain)
            db.session.commit()
            
            # Маскируем имя домена в логах для безопасности
            from modules.telegram_notifier import mask_domain_name
            masked_domain_name = mask_domain_name(domain.name)
            logger.info(f"Added domain {masked_domain_name} to group {group.name}")
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
                # Маскируем имя домена в логах для безопасности
                from modules.telegram_notifier import mask_domain_name
                masked_domain_name = mask_domain_name(domain.name)
                logger.warning(f"Domain {masked_domain_name} is not in group {group.name}")
                return True
                
            # Remove domain from group
            group.domains.remove(domain)
            db.session.commit()
            
            # Маскируем имя домена в логах для безопасности
            from modules.telegram_notifier import mask_domain_name
            masked_domain_name = mask_domain_name(domain.name)
            logger.info(f"Removed domain {masked_domain_name} from group {group.name}")
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
            
    @staticmethod
    def sync_domain_with_ffpanel(domain_id):
        """
        Синхронизирует домен с FFPanel (создание или обновление).
        
        Args:
            domain_id: ID домена для синхронизации
            
        Returns:
            dict: Результат операции {'success': bool, 'message': str}
        """
        try:
            domain = Domain.query.get(domain_id)
            if not domain:
                logger.error(f"Domain with ID {domain_id} not found")
                return {'success': False, 'message': 'Домен не найден'}
            
            # Проверка необходимых параметров
            if not domain.name or not domain.target_ip:
                logger.error(f"Missing required parameters for domain {domain.name}")
                return {'success': False, 'message': 'Отсутствуют обязательные параметры (имя или целевой IP)'}
            
            # Инициализируем API
            api = FFPanelAPI()
            
            # Если домен уже синхронизирован с FFPanel
            if domain.ffpanel_id:
                # Обновляем домен в FFPanel
                dns_records = None  # Здесь можно добавить логику для создания NS-записей
                result = api.update_site(
                    site_id=domain.ffpanel_id,
                    ip_path=domain.target_ip,
                    port=str(domain.target_port),
                    port_out=domain.ffpanel_port_out,
                    port_ssl=domain.ffpanel_port_ssl,
                    port_out_ssl=domain.ffpanel_port_out_ssl,
                    dns=dns_records
                )
                
                if result['success']:
                    domain.ffpanel_status = 'synced'
                    domain.ffpanel_last_sync = datetime.utcnow()
                    db.session.commit()
                    
                    # Маскируем имя домена в логах для безопасности
                    from modules.telegram_notifier import mask_domain_name
                    masked_domain_name = mask_domain_name(domain.name)
                    logger.info(f"Successfully updated domain {masked_domain_name} in FFPanel (ID: {domain.ffpanel_id})")
                    return {'success': True, 'message': 'Домен успешно обновлен в FFPanel'}
                else:
                    domain.ffpanel_status = 'error'
                    db.session.commit()
                    
                    # Маскируем имя домена в логах для безопасности
                    from modules.telegram_notifier import mask_domain_name
                    masked_domain_name = mask_domain_name(domain.name)
                    logger.error(f"Error updating domain {masked_domain_name} in FFPanel: {result['message']}")
                    return {'success': False, 'message': f"Ошибка обновления в FFPanel: {result['message']}"}
            else:
                # Создаем новый домен в FFPanel
                result = api.add_site(
                    domain=domain.name,
                    ip_path=domain.target_ip,
                    port=str(domain.target_port),
                    port_out=domain.ffpanel_port_out or '80',
                    dns=domain.ffpanel_dns or ''
                )
                
                if result['success'] and result['id']:
                    domain.ffpanel_id = result['id']
                    domain.ffpanel_status = 'synced'
                    domain.ffpanel_last_sync = datetime.utcnow()
                    db.session.commit()
                    
                    # Маскируем имя домена в логах для безопасности
                    from modules.telegram_notifier import mask_domain_name
                    masked_domain_name = mask_domain_name(domain.name)
                    logger.info(f"Successfully created domain {masked_domain_name} in FFPanel (ID: {result['id']})")
                    return {'success': True, 'message': 'Домен успешно создан в FFPanel'}
                else:
                    domain.ffpanel_status = 'error'
                    db.session.commit()
                    
                    # Маскируем имя домена в логах для безопасности
                    from modules.telegram_notifier import mask_domain_name
                    masked_domain_name = mask_domain_name(domain.name)
                    logger.error(f"Error creating domain {masked_domain_name} in FFPanel: {result['message']}")
                    return {'success': False, 'message': f"Ошибка создания в FFPanel: {result['message']}"}
                    
        except Exception as e:
            db.session.rollback()
            logger.error(f"Exception in FFPanel sync for domain {domain_id}: {str(e)}")
            return {'success': False, 'message': f"Исключение при синхронизации: {str(e)}"}
            
    @staticmethod
    def delete_domain_from_ffpanel(domain_id):
        """
        Удаляет домен из FFPanel.
        
        Args:
            domain_id: ID домена для удаления
            
        Returns:
            dict: Результат операции {'success': bool, 'message': str}
        """
        try:
            domain = Domain.query.get(domain_id)
            if not domain:
                logger.error(f"Domain with ID {domain_id} not found")
                return {'success': False, 'message': 'Домен не найден'}
            
            # Если домен не синхронизирован с FFPanel, просто успешно завершаем
            if not domain.ffpanel_id:
                # Маскируем имя домена в логах для безопасности
                from modules.telegram_notifier import mask_domain_name
                masked_domain_name = mask_domain_name(domain.name)
                logger.warning(f"Domain {masked_domain_name} is not synced with FFPanel, nothing to delete")
                return {'success': True, 'message': 'Домен не был синхронизирован с FFPanel'}
            
            # Инициализируем API
            api = FFPanelAPI()
            
            # Удаляем домен из FFPanel
            result = api.delete_site(site_id=domain.ffpanel_id)
            
            if result['success']:
                # Сбрасываем поля FFPanel
                domain.ffpanel_id = None
                domain.ffpanel_status = 'not_synced'
                domain.ffpanel_last_sync = datetime.utcnow()
                db.session.commit()
                
                # Маскируем имя домена в логах для безопасности
                from modules.telegram_notifier import mask_domain_name
                masked_domain_name = mask_domain_name(domain.name)
                logger.info(f"Successfully deleted domain {masked_domain_name} from FFPanel")
                return {'success': True, 'message': 'Домен успешно удален из FFPanel'}
            else:
                # Маскируем имя домена в логах для безопасности
                from modules.telegram_notifier import mask_domain_name
                masked_domain_name = mask_domain_name(domain.name)
                logger.error(f"Error deleting domain {masked_domain_name} from FFPanel: {result['message']}")
                return {'success': False, 'message': f"Ошибка удаления из FFPanel: {result['message']}"}
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Exception in FFPanel delete for domain {domain_id}: {str(e)}")
            return {'success': False, 'message': f"Исключение при удалении: {str(e)}"}
            
    @staticmethod
    def import_domains_from_ffpanel():
        """
        Импортирует список доменов из FFPanel в локальную базу данных.
        
        Returns:
            dict: Статистика импорта {'imported': int, 'updated': int, 'failed': int, 'message': str, 'errors': list}
        """
        stats = {'imported': 0, 'updated': 0, 'failed': 0, 'message': '', 'errors': []}
        
        try:
            # Инициализируем API
            api = FFPanelAPI()
            
            # Получаем список доменов из FFPanel
            ffpanel_domains = api.get_sites()
            
            if not ffpanel_domains:
                logger.warning("No domains found in FFPanel or failed to retrieve list")
                stats['message'] = 'Не удалось получить список доменов из FFPanel или список пуст'
                return stats
            
            for ff_domain in ffpanel_domains:
                try:
                    domain_name = ff_domain.get('domain')
                    if not domain_name:
                        error_msg = f"Отсутствует имя домена в ответе FFPanel: {ff_domain}"
                        logger.error(error_msg)
                        stats['errors'].append(error_msg)
                        stats['failed'] += 1
                        continue
                    
                    # Проверяем, существует ли домен в нашей системе
                    existing_domain = Domain.query.filter_by(name=domain_name).first()
                    
                    if existing_domain:
                        # Если домен уже существует, обновляем его параметры FFPanel
                        existing_domain.ffpanel_id = ff_domain.get('id')
                        existing_domain.ffpanel_status = 'synced'
                        existing_domain.ffpanel_port = ff_domain.get('port', '80')
                        existing_domain.ffpanel_port_out = ff_domain.get('port_out', '80')
                        existing_domain.ffpanel_port_ssl = ff_domain.get('port_ssl', '443')
                        existing_domain.ffpanel_port_out_ssl = ff_domain.get('port_out_ssl', '443')
                        existing_domain.ffpanel_dns = ff_domain.get('dns', '')
                        existing_domain.ffpanel_last_sync = datetime.utcnow()
                        
                        # Если у нас не установлен target_ip, добавим его из FFPanel
                        if not existing_domain.target_ip:
                            existing_domain.target_ip = ff_domain.get('ip', '')
                            
                        # Если у нас не установлены ожидаемые NS-записи, но они есть в FFPanel,
                        # добавляем их в expected_nameservers
                        if not existing_domain.expected_nameservers and ff_domain.get('dns'):
                            existing_domain.expected_nameservers = ff_domain.get('dns')
                        
                        db.session.commit()
                        
                        # Маскируем имя домена в логах для безопасности
                        from modules.telegram_notifier import mask_domain_name
                        masked_domain_name = mask_domain_name(domain_name)
                        logger.info(f"Updated domain {masked_domain_name} from FFPanel (ID: {existing_domain.ffpanel_id})")
                        stats['updated'] += 1
                    else:
                        # Если домен не существует, создаем новый
                        ffpanel_dns = ff_domain.get('dns', '')
                        new_domain = Domain(
                            name=domain_name,
                            target_ip=ff_domain.get('ip', ''),
                            target_port=int(ff_domain.get('port', 80)),
                            ffpanel_id=ff_domain.get('id'),
                            ffpanel_status='synced',
                            ffpanel_port=ff_domain.get('port', '80'),
                            ffpanel_port_out=ff_domain.get('port_out', '80'),
                            ffpanel_port_ssl=ff_domain.get('port_ssl', '443'),
                            ffpanel_port_out_ssl=ff_domain.get('port_out_ssl', '443'),
                            ffpanel_dns=ffpanel_dns,
                            expected_nameservers=ffpanel_dns,  # Заполняем ожидаемые NS-записи из FFPanel
                            ffpanel_last_sync=datetime.utcnow()
                        )
                        
                        db.session.add(new_domain)
                        db.session.commit()
                        
                        # Маскируем имя домена в логах для безопасности
                        from modules.telegram_notifier import mask_domain_name
                        masked_domain_name = mask_domain_name(domain_name)
                        logger.info(f"Imported new domain {masked_domain_name} from FFPanel (ID: {new_domain.ffpanel_id})")
                        stats['imported'] += 1
                        
                except Exception as e:
                    db.session.rollback()
                    
                    # Получаем имя домена и маскируем его для безопасности
                    domain_name_for_error = ff_domain.get('domain', 'Неизвестно')
                    if domain_name_for_error != 'Неизвестно':
                        from modules.telegram_notifier import mask_domain_name
                        masked_domain_name = mask_domain_name(domain_name_for_error)
                        error_msg = f"Ошибка при обработке домена {masked_domain_name}: {str(e)}"
                    else:
                        error_msg = f"Ошибка при обработке домена Неизвестно: {str(e)}"
                        
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)
                    stats['failed'] += 1
            
            stats['message'] = f"Импорт завершен. Импортировано новых: {stats['imported']}, обновлено: {stats['updated']}, ошибок: {stats['failed']}"
            return stats
            
        except Exception as e:
            error_msg = f"Исключение при импорте доменов из FFPanel: {str(e)}"
            logger.error(error_msg)
            stats['errors'].append(error_msg)
            stats['message'] = f"Ошибка при импорте доменов: {str(e)}"
            return stats
