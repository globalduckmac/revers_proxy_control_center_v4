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
    
    def __init__(self, token=None):
        """
        Инициализация с токеном API.
        
        Args:
            token: Токен для доступа к API (если None, берется из настроек или переменных окружения)
        """
        self.token = token
        self.jwt_token = None
        self.jwt_expire = 0
        
        # Если токен не указан, пытаемся получить его из настроек или переменных окружения
        if not self.token:
            try:
                from models import SystemSetting
                from flask import current_app
                
                # Получаем токен из SystemSetting
                self.token = SystemSetting.get_value('ffpanel_token')
                
                # Если не нашли в настройках, проверяем переменные окружения
                if not self.token:
                    self.token = os.environ.get('FFPANEL_TOKEN')
                    
                # Логируем информацию о токене    
                if self.token:
                    current_app.logger.info(f"FFPanel токен найден, длина: {len(self.token)}")
                else:
                    current_app.logger.warning("Токен FFPanel не найден ни в настройках, ни в переменных окружения")
            except Exception as e:
                from flask import current_app
                current_app.logger.error(f"Ошибка при получении токена FFPanel: {str(e)}")
                # Пробуем использовать переменную окружения как запасной вариант
                self.token = os.environ.get('FFPANEL_TOKEN')
        
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
                current_app.logger.error(f"FFPanel аутентификация неудачна: {data.get('message', 'Неизвестная ошибка')}")
                return False
        except Exception as e:
            current_app.logger.error(f"Ошибка аутентификации FFPanel: {str(e)}")
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
            response = requests.get(f"{self.API_URL}/list.site", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('domains', [])
            elif response.status_code == 404:
                # Нет данных
                return []
            else:
                current_app.logger.error(f"Ошибка получения списка сайтов: {response.text}")
                return []
        except Exception as e:
            current_app.logger.error(f"Ошибка при запросе списка сайтов: {str(e)}")
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
            
            response = requests.post(f"{self.API_URL}/add.site", headers=headers, data=data)
            result = response.json()
            
            if response.status_code == 200 and result.get('code') == 200:
                return {
                    'success': True,
                    'id': result.get('id'),
                    'message': 'Сайт успешно добавлен'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                current_app.logger.error(f"Ошибка добавления сайта: {error_message}")
                return {
                    'success': False,
                    'id': None,
                    'message': f"Ошибка: {error_message}"
                }
        except Exception as e:
            current_app.logger.error(f"Исключение при добавлении сайта: {str(e)}")
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
            
            response = requests.post(f"{self.API_URL}/update.site", headers=headers, data=data)
            result = response.json()
            
            if response.status_code == 200 and result.get('code') == 200:
                return {
                    'success': True,
                    'message': 'Сайт успешно обновлен'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                current_app.logger.error(f"Ошибка обновления сайта: {error_message}")
                return {
                    'success': False,
                    'message': f"Ошибка: {error_message}"
                }
        except Exception as e:
            current_app.logger.error(f"Исключение при обновлении сайта: {str(e)}")
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
            
            response = requests.post(f"{self.API_URL}/delete.site", headers=headers, data=data)
            result = response.json()
            
            if response.status_code == 200 and result.get('code') == 200:
                return {
                    'success': True,
                    'message': 'Сайт успешно удален'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                current_app.logger.error(f"Ошибка удаления сайта: {error_message}")
                return {
                    'success': False,
                    'message': f"Ошибка: {error_message}"
                }
        except Exception as e:
            current_app.logger.error(f"Исключение при удалении сайта: {str(e)}")
            return {
                'success': False,
                'message': f"Исключение: {str(e)}"
            }