"""
Модуль для интеграции с FFPanel API.

Функции для работы с API FFPanel:
- Аутентификация
- Получение списка доменов
- Добавление доменов
- Обновление доменов
- Удаление доменов
"""

import json
import logging
import os
import requests
from datetime import datetime, timedelta
from flask import current_app


logger = logging.getLogger(__name__)


class FFPanelAPI:
    """Класс для работы с FFPanel API."""
    
    def __init__(self, token=None):
        """
        Инициализация API-клиента для FFPanel.
        
        Args:
            token (str, optional): Токен доступа к API FFPanel. 
                                 Если не указан, будет использован FFPANEL_TOKEN из переменных окружения.
        """
        self.base_url = "https://ffv2.ru"
        self.api_url = f"{self.base_url}/api"
        self.public_api_url = f"{self.base_url}/public/api"
        self.token = token or os.environ.get('FFPANEL_TOKEN')
        self.jwt_token = None
        self.jwt_expiration = None
        
        if not self.token:
            logger.warning("FFPANEL_TOKEN не найден в переменных окружения")
    
    def authenticate(self):
        """
        Аутентификация и получение JWT-токена.
        
        Returns:
            bool: True, если аутентификация прошла успешно, иначе False.
        """
        # Проверяем, не истёк ли текущий токен
        if self.jwt_token and self.jwt_expiration and datetime.now() < self.jwt_expiration:
            return True
        
        if not self.token:
            logger.error("Отсутствует токен FFPanel")
            return False
        
        try:
            params = {
                'method': 'auth',
                'token': self.token
            }
            
            response = requests.get(self.public_api_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get('code') == 200 and 'token' in data:
                self.jwt_token = data['token']['jwt']
                
                # Расчёт времени истечения токена (добавляем запас в 5 минут на всякий случай)
                expiration_timestamp = data['token']['expire']
                self.jwt_expiration = datetime.fromtimestamp(expiration_timestamp) - timedelta(minutes=5)
                
                logger.info("Успешная аутентификация в FFPanel API")
                return True
            else:
                logger.error(f"Ошибка при аутентификации в FFPanel API: {data.get('message', 'Неизвестная ошибка')}")
                return False
        except requests.RequestException as e:
            logger.error(f"Ошибка соединения с FFPanel API: {str(e)}")
            return False
        except (ValueError, KeyError) as e:
            logger.error(f"Ошибка обработки ответа FFPanel API: {str(e)}")
            return False
    
    def get_authorization_header(self):
        """
        Получение заголовка авторизации с JWT-токеном.
        
        Returns:
            dict: Заголовок авторизации для запросов к API.
        """
        if not self.authenticate():
            return {}
        
        return {
            'Authorization': f'Bearer {self.jwt_token}'
        }
    
    def get_domains(self):
        """
        Получение списка доменов из FFPanel.
        
        Returns:
            list: Список словарей с информацией о доменах, или пустой список в случае ошибки.
        """
        headers = self.get_authorization_header()
        if not headers:
            return []
        
        try:
            url = f"{self.api_url}/list.site"
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if data.get('code') == 200 and 'domains' in data:
                logger.info(f"Получено {len(data['domains'])} доменов из FFPanel")
                return data['domains']
            elif data.get('code') == 404:
                logger.info("Домены в FFPanel не найдены")
                return []
            else:
                logger.error(f"Ошибка при получении списка доменов из FFPanel: {data.get('message', 'Неизвестная ошибка')}")
                return []
        except requests.RequestException as e:
            logger.error(f"Ошибка соединения с FFPanel API при получении списка доменов: {str(e)}")
            return []
        except (ValueError, KeyError) as e:
            logger.error(f"Ошибка обработки ответа FFPanel API при получении списка доменов: {str(e)}")
            return []
    
    def add_domain(self, domain, ip, port=80, port_out=80, dns="ns1.digitalocean.com"):
        """
        Добавление нового домена в FFPanel.
        
        Args:
            domain (str): Доменное имя.
            ip (str): IP-адрес сервера.
            port (int, optional): Порт для подключения. По умолчанию 80.
            port_out (int, optional): Внешний порт. По умолчанию 80.
            dns (str, optional): DNS-сервер. По умолчанию "ns1.digitalocean.com".
            
        Returns:
            dict: Словарь с информацией о результате операции.
                'success' (bool): True, если операция успешна, иначе False.
                'message' (str): Сообщение о результате операции.
                'domain_id' (int): ID добавленного домена, если операция успешна.
        """
        headers = self.get_authorization_header()
        if not headers:
            return {'success': False, 'message': 'Ошибка аутентификации в FFPanel', 'domain_id': None}
        
        try:
            url = f"{self.api_url}/add.site"
            
            data = {
                'domain': domain,
                'ip_path': ip,
                'port': str(port),
                'port_out': str(port_out),
                'dns': dns
            }
            
            response = requests.post(url, data=data, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            if result.get('code') == 200:
                domain_id = result.get('id')
                logger.info(f"Домен {domain} успешно добавлен в FFPanel (ID: {domain_id})")
                return {'success': True, 'message': 'Домен успешно добавлен', 'domain_id': domain_id}
            else:
                logger.error(f"Ошибка при добавлении домена {domain} в FFPanel: {result.get('message', 'Неизвестная ошибка')}")
                return {'success': False, 'message': result.get('message', 'Ошибка при добавлении домена'), 'domain_id': None}
        except requests.RequestException as e:
            logger.error(f"Ошибка соединения с FFPanel API при добавлении домена {domain}: {str(e)}")
            return {'success': False, 'message': f'Ошибка соединения: {str(e)}', 'domain_id': None}
        except (ValueError, KeyError) as e:
            logger.error(f"Ошибка обработки ответа FFPanel API при добавлении домена {domain}: {str(e)}")
            return {'success': False, 'message': f'Ошибка обработки ответа: {str(e)}', 'domain_id': None}
    
    def update_domain(self, domain_id, ip, port=80, port_out=80, port_ssl=443, port_out_ssl=443, wildcard=0, dns_records=None):
        """
        Обновление домена в FFPanel.
        
        Args:
            domain_id (int): ID домена в FFPanel.
            ip (str): Новый IP-адрес сервера.
            port (int, optional): Порт для подключения. По умолчанию 80.
            port_out (int, optional): Внешний порт. По умолчанию 80.
            port_ssl (int, optional): SSL порт. По умолчанию 443.
            port_out_ssl (int, optional): Внешний SSL порт. По умолчанию 443.
            wildcard (int, optional): Флаг использования wildcard сертификата. По умолчанию 0.
            dns_records (list, optional): Список DNS-записей для домена. По умолчанию None.
            
        Returns:
            dict: Словарь с информацией о результате операции.
                'success' (bool): True, если операция успешна, иначе False.
                'message' (str): Сообщение о результате операции.
        """
        headers = self.get_authorization_header()
        if not headers:
            return {'success': False, 'message': 'Ошибка аутентификации в FFPanel'}
        
        try:
            url = f"{self.api_url}/update.site"
            
            dns_data = dns_records or []
            if not isinstance(dns_data, list):
                dns_data = []
                
            data = {
                'id': domain_id,
                'ip_path': ip,
                'port': str(port),
                'port_out': str(port_out),
                'port_ssl': str(port_ssl),
                'port_out_ssl': str(port_out_ssl),
                'real_ip': ip,
                'wildcard': str(wildcard),
                'dns': json.dumps(dns_data)
            }
            
            response = requests.post(url, data=data, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            if result.get('code') == 200:
                logger.info(f"Домен (ID: {domain_id}) успешно обновлен в FFPanel")
                return {'success': True, 'message': 'Домен успешно обновлен'}
            else:
                logger.error(f"Ошибка при обновлении домена (ID: {domain_id}) в FFPanel: {result.get('message', 'Неизвестная ошибка')}")
                return {'success': False, 'message': result.get('message', 'Ошибка при обновлении домена')}
        except requests.RequestException as e:
            logger.error(f"Ошибка соединения с FFPanel API при обновлении домена (ID: {domain_id}): {str(e)}")
            return {'success': False, 'message': f'Ошибка соединения: {str(e)}'}
        except (ValueError, KeyError) as e:
            logger.error(f"Ошибка обработки ответа FFPanel API при обновлении домена (ID: {domain_id}): {str(e)}")
            return {'success': False, 'message': f'Ошибка обработки ответа: {str(e)}'}
    
    def delete_domain(self, domain_id):
        """
        Удаление домена из FFPanel.
        
        Args:
            domain_id (int): ID домена в FFPanel.
            
        Returns:
            dict: Словарь с информацией о результате операции.
                'success' (bool): True, если операция успешна, иначе False.
                'message' (str): Сообщение о результате операции.
        """
        headers = self.get_authorization_header()
        if not headers:
            return {'success': False, 'message': 'Ошибка аутентификации в FFPanel'}
        
        try:
            url = f"{self.api_url}/delete.site"
            
            data = {
                'id': domain_id
            }
            
            response = requests.post(url, data=data, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            if result.get('code') == 200:
                logger.info(f"Домен (ID: {domain_id}) успешно удален из FFPanel")
                return {'success': True, 'message': 'Домен успешно удален'}
            else:
                logger.error(f"Ошибка при удалении домена (ID: {domain_id}) из FFPanel: {result.get('message', 'Неизвестная ошибка')}")
                return {'success': False, 'message': result.get('message', 'Ошибка при удалении домена')}
        except requests.RequestException as e:
            logger.error(f"Ошибка соединения с FFPanel API при удалении домена (ID: {domain_id}): {str(e)}")
            return {'success': False, 'message': f'Ошибка соединения: {str(e)}'}
        except (ValueError, KeyError) as e:
            logger.error(f"Ошибка обработки ответа FFPanel API при удалении домена (ID: {domain_id}): {str(e)}")
            return {'success': False, 'message': f'Ошибка обработки ответа: {str(e)}'}


# Создаем синглтон для использования в приложении
def get_ffpanel_api():
    """
    Получение экземпляра FFPanelAPI.
    
    Returns:
        FFPanelAPI: Экземпляр класса FFPanelAPI.
    """
    token = os.environ.get('FFPANEL_TOKEN')
    return FFPanelAPI(token=token)