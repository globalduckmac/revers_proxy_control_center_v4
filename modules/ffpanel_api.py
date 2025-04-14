"""
Модуль для интеграции с FFPanel API.
Позволяет получать и управлять доменами через FFPanel API.
"""

import os
import json
import time
import requests
from datetime import datetime
from flask import current_app

class FFPanelAPI:
    """
    Класс для работы с FFPanel API.
    Обеспечивает аутентификацию и вызов методов API.
    """
    BASE_URL = "https://ffv2.ru"
    AUTH_URL = f"{BASE_URL}/public/api"
    API_URL = f"{BASE_URL}/api"
    
    def __init__(self, token=None, logger=None):
        """
        Инициализация с токеном API.
        
        Args:
            token: Токен для доступа к API (если None, берется из настроек или переменных окружения)
            logger: Логгер для записи информации (если None, будет создан стандартный логгер)
        """
        self.token = token
        self.jwt_token = None
        self.jwt_expire = 0
        
        # Настраиваем логгер
        self.logger = logger
        if self.logger is None:
            import logging
            self.logger = logging.getLogger('ffpanel_api')
            if not self.logger.handlers:  # Если нет обработчиков, добавляем их
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
        
        # Если токен не указан, пытаемся получить его из настроек или переменных окружения
        if not self.token:
            # Сначала попробуем получить из переменных окружения
            self.token = os.environ.get('FFPANEL_TOKEN')
            
            # Если не нашли, пробуем получить из системных настроек
            if not self.token:
                try:
                    from models import SystemSetting
                    self.token = SystemSetting.get_value('ffpanel_token')
                except Exception as e:
                    self.logger.error(f"Ошибка при получении токена FFPanel из SystemSetting: {str(e)}")
            
            # Логируем информацию о токене    
            if self.token:
                self.logger.info(f"FFPanel токен найден, длина: {len(self.token)}")
            else:
                self.logger.warning("Токен FFPanel не найден ни в настройках, ни в переменных окружения")
        
    def _authenticate(self):
        """
        Аутентификация в API и получение JWT-токена.
        
        Returns:
            bool: True если аутентификация успешна, иначе False
        """
        if self.jwt_token and self.jwt_expire > time.time():
            # Используем существующий токен, если он еще действителен
            return True
            
        try:
            params = {
                'method': 'auth',
                'token': self.token
            }
            response = requests.get(self.AUTH_URL, params=params)
            data = response.json()
            
            if response.status_code == 200 and 'token' in data:
                self.jwt_token = data['token']['jwt']
                self.jwt_expire = data['token']['expire']
                return True
            else:
                self.logger.error(f"FFPanel аутентификация неудачна: {data.get('message', 'Неизвестная ошибка')}")
                return False
        except Exception as e:
            self.logger.error(f"Ошибка аутентификации FFPanel: {str(e)}")
            return False
    
    def _get_headers(self):
        """
        Получение заголовков для API запросов.
        
        Returns:
            dict: Заголовки с авторизацией
        """
        if not self._authenticate():
            raise Exception("Не удалось получить JWT-токен для доступа к API")
            
        return {
            'Authorization': f'Bearer {self.jwt_token}',
            'Content-Type': 'application/json'
        }
    
    def get_sites(self):
        """
        Получение списка сайтов из FFPanel.
        
        Returns:
            list: Список доменов или пустой список в случае ошибки
        """
        try:
            headers = self._get_headers()
            self.logger.debug(f"Отправка запроса на получение списка сайтов")
            response = requests.get(f"{self.API_URL}/list.site", headers=headers)
            self.logger.debug(f"Получен ответ от FFPanel: {response.status_code}")
            
            try:
                data = response.json()
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text}")
                return []
            
            if response.status_code == 200:
                domains = data.get('domains', [])
                self.logger.info(f"Получено {len(domains)} доменов из FFPanel")
                return domains
            elif response.status_code == 404:
                self.logger.info("Список сайтов в FFPanel пуст (код 404)")
                return []
            else:
                error_message = data.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка получения списка сайтов (код {response.status_code}): {error_message}")
                return []
        except Exception as e:
            self.logger.exception(f"Исключение при запросе списка сайтов: {str(e)}")
            return []
    
    def add_site(self, domain, ip_path, port="80", port_out="80", dns=""):
        """
        Добавление нового сайта в FFPanel.
        
        Args:
            domain: Доменное имя
            ip_path: IP адрес или путь
            port: Порт для подключения (по умолчанию 80)
            port_out: Внешний порт (по умолчанию 80)
            dns: DNS-адрес
            
        Returns:
            dict: Словарь с результатом операции: {'success': bool, 'id': int или None, 'message': str}
        """
        try:
            headers = self._get_headers()
            headers.pop('Content-Type', None)  # Убираем Content-Type для multipart/form-data
            
            data = {
                'domain': domain,
                'ip_path': ip_path,
                'port': port,
                'port_out': port_out,
                'dns': dns
            }
            
            self.logger.debug(f"Отправка запроса на добавление сайта: {domain}, IP: {ip_path}, порт: {port}")
            response = requests.post(f"{self.API_URL}/add.site", headers=headers, data=data)
            self.logger.debug(f"Получен ответ от FFPanel: {response.status_code}, текст: {response.text}")
            
            try:
                result = response.json()
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text}")
                return {
                    'success': False,
                    'id': None,
                    'message': f"Ошибка при разборе ответа: {response.text}"
                }
            
            if response.status_code == 200 and result.get('code') == 200:
                self.logger.info(f"Сайт {domain} успешно добавлен в FFPanel, ID: {result.get('id')}")
                return {
                    'success': True,
                    'id': result.get('id'),
                    'message': 'Сайт успешно добавлен'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка добавления сайта: {error_message}, код: {result.get('code')}")
                return {
                    'success': False,
                    'id': None,
                    'message': f"Ошибка: {error_message}"
                }
        except Exception as e:
            self.logger.exception(f"Исключение при добавлении сайта: {str(e)}")
            return {
                'success': False,
                'id': None,
                'message': f"Исключение: {str(e)}"
            }
    
    def update_site(self, site_id, ip_path, port="80", port_out="80", port_ssl="443", 
                    port_out_ssl="443", real_ip="", wildcard="0", dns=None):
        """
        Обновление сайта в FFPanel.
        
        Args:
            site_id: ID сайта
            ip_path: IP адрес или путь
            port: Порт для подключения
            port_out: Внешний порт
            port_ssl: SSL порт
            port_out_ssl: Внешний SSL порт
            real_ip: Реальный IP
            wildcard: Флаг wildcard (0 или 1)
            dns: Список DNS-записей (список словарей)
            
        Returns:
            dict: Словарь с результатом операции: {'success': bool, 'message': str}
        """
        try:
            headers = self._get_headers()
            headers.pop('Content-Type', None)  # Убираем Content-Type для multipart/form-data
            
            data = {
                'id': site_id,
                'ip_path': ip_path,
                'port': port,
                'port_out': port_out,
                'port_ssl': port_ssl,
                'port_out_ssl': port_out_ssl,
                'real_ip': real_ip,
                'wildcard': wildcard,
            }
            
            if dns:
                data['dns'] = json.dumps(dns)
            
            self.logger.debug(f"Отправка запроса на обновление сайта с ID: {site_id}, IP: {ip_path}, порт: {port}")
            response = requests.post(f"{self.API_URL}/update.site", headers=headers, data=data)
            self.logger.debug(f"Получен ответ от FFPanel: {response.status_code}, текст: {response.text}")
            
            try:
                result = response.json()
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text}")
                return {
                    'success': False,
                    'message': f"Ошибка при разборе ответа: {response.text}"
                }
            
            if response.status_code == 200 and result.get('code') == 200:
                self.logger.info(f"Сайт с ID {site_id} успешно обновлен в FFPanel")
                return {
                    'success': True,
                    'message': 'Сайт успешно обновлен'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка обновления сайта: {error_message}, код: {result.get('code')}")
                return {
                    'success': False,
                    'message': f"Ошибка: {error_message}"
                }
        except Exception as e:
            self.logger.exception(f"Исключение при обновлении сайта: {str(e)}")
            return {
                'success': False,
                'message': f"Исключение: {str(e)}"
            }
    
    def delete_site(self, site_id):
        """
        Удаление сайта из FFPanel.
        
        Args:
            site_id: ID сайта для удаления
            
        Returns:
            dict: Словарь с результатом операции: {'success': bool, 'message': str}
        """
        try:
            headers = self._get_headers()
            headers.pop('Content-Type', None)  # Убираем Content-Type для multipart/form-data
            
            data = {
                'id': site_id
            }
            
            self.logger.debug(f"Отправка запроса на удаление сайта с ID: {site_id}")
            response = requests.post(f"{self.API_URL}/delete.site", headers=headers, data=data)
            self.logger.debug(f"Получен ответ от FFPanel: {response.status_code}, текст: {response.text}")
            
            try:
                result = response.json()
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text}")
                return {
                    'success': False,
                    'message': f"Ошибка при разборе ответа: {response.text}"
                }
            
            if response.status_code == 200 and result.get('code') == 200:
                self.logger.info(f"Сайт с ID {site_id} успешно удален из FFPanel")
                return {
                    'success': True,
                    'message': 'Сайт успешно удален'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка удаления сайта: {error_message}, код: {result.get('code')}")
                return {
                    'success': False,
                    'message': f"Ошибка: {error_message}"
                }
        except Exception as e:
            self.logger.exception(f"Исключение при удалении сайта: {str(e)}")
            return {
                'success': False,
                'message': f"Исключение: {str(e)}"
            }