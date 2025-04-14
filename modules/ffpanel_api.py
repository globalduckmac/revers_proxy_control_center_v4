"""
Модуль для интеграции с FFPanel API.
Позволяет получать и управлять доменами через FFPanel API.
"""

import os
import json
import time
import requests
import logging
from datetime import datetime

# Специальный класс логгера для FFPanelAPI
class FFPanelLogger:
    """
    Специальный класс для логирования в FFPanelAPI,
    который может работать как с Flask логгером, так и с обычным Python логгером.
    """
    def __init__(self, logger=None):
        """
        Инициализация логгера.
        
        Args:
            logger: Объект логгера или None для использования стандартного логгера
        """
        if logger:
            self.logger = logger
        else:
            try:
                from flask import current_app
                self.logger = current_app.logger
            except (ImportError, RuntimeError):
                # Если Flask не импортируется или нет активного контекста приложения,
                # создаем стандартный логгер Python
                self.logger = logging.getLogger('ffpanel_api')
                if not self.logger.handlers:
                    handler = logging.StreamHandler()
                    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                    handler.setFormatter(formatter)
                    self.logger.addHandler(handler)
                    self.logger.setLevel(logging.INFO)
    
    def debug(self, message):
        """Запись отладочного сообщения"""
        if self.logger:
            self.logger.debug(message)
    
    def info(self, message):
        """Запись информационного сообщения"""
        if self.logger:
            self.logger.info(message)
    
    def warning(self, message):
        """Запись предупреждения"""
        if self.logger:
            self.logger.warning(message)
    
    def error(self, message):
        """Запись сообщения об ошибке"""
        if self.logger:
            self.logger.error(message)
    
    def exception(self, message):
        """Запись исключения с трассировкой стека"""
        if self.logger:
            self.logger.exception(message)

try:
    from flask import current_app
except ImportError:
    current_app = None

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
        self.jwt_expire = 0  # время истечения токена
        
        # Инициализируем логгер через FFPanelLogger
        if logger is None:
            self.logger = FFPanelLogger()
        elif isinstance(logger, FFPanelLogger):
            self.logger = logger
        else:
            self.logger = FFPanelLogger(logger)
            
        # Добавляем подробное логирование для отладки
        self.logger.debug(f"FFPanelAPI инициализирован с BASE_URL: {self.BASE_URL}")
        
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
        Аутентификация в API и получение JWT-токена согласно документации FFPanel API.
        
        Returns:
            bool: True если аутентификация успешна, иначе False
        """
        # Если у нас уже есть JWT токен и он не истек, возвращаем True
        if self.jwt_token and hasattr(self, 'jwt_expire') and self.jwt_expire > time.time():
            self.logger.debug(f"Используем существующий JWT токен (действителен до {datetime.fromtimestamp(self.jwt_expire)})")
            return True
            
        try:
            # Формируем тело запроса согласно документации
            payload = {'token': self.token}
            headers = {'Content-Type': 'application/json'}
            
            # Отправляем запрос на аутентификацию
            self.logger.debug(f"Отправка запроса аутентификации к {self.AUTH_URL}")
            self.logger.debug(f"Заголовки: {headers}")
            
            response = requests.post(self.AUTH_URL, json=payload, headers=headers)
            
            self.logger.debug(f"Получен ответ: {response.status_code}")
            self.logger.debug(f"Заголовки ответа: {response.headers}")
            
            # Проверяем успешность запроса
            if response.status_code != 200:
                self.logger.error(f"Ошибка аутентификации HTTP: {response.status_code}, {response.text[:200]}")
                return False
                
            # Разбираем ответ
            try:
                data = response.json()
                self.logger.debug(f"Данные ответа: {data}")
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text[:200]}")
                return False
            
            # Получаем JWT токен
            token = data.get('token')
            if not token:
                self.logger.error("JWT токен не найден в ответе")
                return False
                
            # Сохраняем токен
            self.jwt_token = token
            
            # Устанавливаем время истечения токена из поля expire
            if 'expire' in data:
                self.jwt_expire = int(data['expire'])
                self.logger.info(f"JWT токен получен, истекает: {datetime.fromtimestamp(self.jwt_expire)}")
            else:
                # Если время истечения не указано, устанавливаем +24 часа от текущего времени
                self.jwt_expire = int(time.time()) + 24*60*60
                self.logger.warning(f"Время истечения токена не найдено в ответе, установлено стандартное: {datetime.fromtimestamp(self.jwt_expire)}")
            
            # Для совместимости с остальным кодом
            self.jwt_expires = datetime.fromtimestamp(self.jwt_expire)
            
            return True
        except Exception as e:
            self.logger.exception(f"Исключение при аутентификации FFPanel: {str(e)}")
            return False
    
    def _get_headers(self):
        """
        Получение заголовков для API запросов согласно документации FFPanel API.
        
        Returns:
            dict: Заголовки с авторизацией
        """
        if not self._authenticate():
            self.logger.error("Не удалось получить JWT-токен для доступа к API")
            raise Exception("Не удалось получить JWT-токен для доступа к API")
            
        # Заголовки согласно документации API
        headers = {
            'Authorization': f'Bearer {self.jwt_token}',
            'Accept': 'application/json'  # Используем Accept вместо Content-Type для запросов GET
        }
        
        self.logger.debug(f"Сформированы заголовки для API запроса: {headers}")
        return headers
    
    def get_sites(self):
        """
        Получение списка сайтов из FFPanel согласно документации API.
        URL: https://ffv2.ru/api/list.site
        Метод: GET
        
        Returns:
            list: Список доменов или пустой список в случае ошибки
        """
        try:
            # Получаем заголовки с авторизацией
            headers = self._get_headers()
            url = f"{self.API_URL}/list.site"
            
            self.logger.debug(f"Отправка запроса на получение списка сайтов: {url}")
            self.logger.debug(f"Заголовки запроса: {headers}")
            
            # Выполняем GET запрос согласно документации
            response = requests.get(url, headers=headers)
            
            self.logger.debug(f"Получен ответ от FFPanel: {response.status_code}")
            self.logger.debug(f"Заголовки ответа: {response.headers}")
            
            # Пытаемся разобрать JSON ответ
            try:
                data = response.json()
                self.logger.debug(f"Получены данные: {data.keys() if data else 'Пустой ответ'}")
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text[:200]}...")
                return []
            
            # Обрабатываем ответ согласно его коду
            if response.status_code == 200:
                domains = data.get('domains', [])
                self.logger.info(f"Получено {len(domains)} доменов из FFPanel")
                
                # Выводим информацию о первых 3 доменах для отладки
                if domains and len(domains) > 0:
                    sample_domains = domains[:3]
                    for i, domain in enumerate(sample_domains):
                        self.logger.debug(f"Домен {i+1}: ID={domain.get('id')}, Имя={domain.get('domain')}")
                
                return domains
            elif response.status_code == 404:
                self.logger.info("Список сайтов в FFPanel пуст (код 404)")
                return []
            else:
                error_message = data.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка получения списка сайтов (код {response.status_code}): {error_message}")
                self.logger.error(f"Полный ответ: {response.text[:300]}...")
                return []
        except Exception as e:
            self.logger.exception(f"Исключение при запросе списка сайтов: {str(e)}")
            return []
            
    def get_site(self, site_id):
        """
        Получение информации о конкретном сайте по его ID.
        Так как API FFPanel не предоставляет метод для получения одного сайта,
        мы получаем список всех сайтов и ищем нужный по ID.
        
        Args:
            site_id: ID сайта в FFPanel
            
        Returns:
            dict: Словарь с данными сайта или None, если сайт не найден
        """
        self.logger.debug(f"Запрос информации о сайте с ID: {site_id}")
        
        try:
            # Получаем список всех сайтов
            sites = self.get_sites()
            
            if not sites:
                self.logger.warning(f"Не удалось получить список сайтов для поиска сайта с ID: {site_id}")
                return None
            
            # Ищем сайт по ID
            for site in sites:
                if site.get('id') == site_id:
                    self.logger.info(f"Найден сайт с ID {site_id}: {site.get('domain')}")
                    return {
                        'success': True,
                        'data': site
                    }
            
            self.logger.warning(f"Сайт с ID {site_id} не найден в списке сайтов FFPanel")
            return None
        except Exception as e:
            self.logger.exception(f"Исключение при получении информации о сайте {site_id}: {str(e)}")
            return None
    
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
            # Получаем заголовки с авторизацией
            headers = self._get_headers()
            
            # Для POST запросов с формой нужно установить Content-Type: application/x-www-form-urlencoded
            # и удалить Accept если он добавлен методом _get_headers
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            headers.pop('Accept', None)
            
            # Подготавливаем данные для запроса
            data = {
                'domain': domain,
                'ip_path': ip_path,
                'port': port,
                'port_out': port_out,
                'dns': dns
            }
            
            url = f"{self.API_URL}/add.site"
            self.logger.debug(f"Отправка запроса на добавление сайта: {url}")
            self.logger.debug(f"Параметры запроса: {data}")
            self.logger.debug(f"Заголовки запроса: {headers}")
            
            # Выполняем POST запрос согласно документации API
            response = requests.post(url, headers=headers, data=data)
            
            self.logger.debug(f"Получен ответ от FFPanel: {response.status_code}")
            self.logger.debug(f"Заголовки ответа: {response.headers}")
            self.logger.debug(f"Текст ответа: {response.text}")
            
            # Пытаемся разобрать JSON ответ
            try:
                result = response.json()
                self.logger.debug(f"Получены данные: {result}")
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text[:200]}...")
                return {
                    'success': False,
                    'id': None,
                    'message': f"Ошибка при разборе ответа: {response.text[:100]}..."
                }
            
            # Проверяем код ответа и код в теле ответа (может отличаться)
            response_code = result.get('code', 0)
            
            if response.status_code == 200 and (response_code == 200 or response_code == 0):
                site_id = result.get('id')
                self.logger.info(f"Сайт {domain} успешно добавлен в FFPanel, ID: {site_id}")
                return {
                    'success': True,
                    'id': site_id,
                    'message': 'Сайт успешно добавлен'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка добавления сайта: {error_message}, HTTP код: {response.status_code}, API код: {response_code}")
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
            # Получаем заголовки с авторизацией
            headers = self._get_headers()
            
            # Для POST запросов с формой нужно установить Content-Type: application/x-www-form-urlencoded
            # и удалить Accept если он добавлен методом _get_headers
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            headers.pop('Accept', None)
            
            # Подготавливаем данные для запроса
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
            
            # Добавляем JSON с записями DNS, если они предоставлены
            if dns:
                data['dns'] = json.dumps(dns)
            
            url = f"{self.API_URL}/update.site"
            self.logger.debug(f"Отправка запроса на обновление сайта: {url}")
            self.logger.debug(f"Параметры запроса: {data}")
            self.logger.debug(f"Заголовки запроса: {headers}")
            
            # Выполняем POST запрос согласно документации API
            response = requests.post(url, headers=headers, data=data)
            
            self.logger.debug(f"Получен ответ от FFPanel: {response.status_code}")
            self.logger.debug(f"Заголовки ответа: {response.headers}")
            self.logger.debug(f"Текст ответа: {response.text}")
            
            # Пытаемся разобрать JSON ответ
            try:
                result = response.json()
                self.logger.debug(f"Получены данные: {result}")
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text[:200]}...")
                return {
                    'success': False,
                    'message': f"Ошибка при разборе ответа: {response.text[:100]}..."
                }
            
            # Проверяем код ответа и код в теле ответа (может отличаться)
            response_code = result.get('code', 0)
            
            if response.status_code == 200 and (response_code == 200 or response_code == 0):
                self.logger.info(f"Сайт с ID {site_id} успешно обновлен в FFPanel")
                return {
                    'success': True,
                    'message': 'Сайт успешно обновлен'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка обновления сайта: {error_message}, HTTP код: {response.status_code}, API код: {response_code}")
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
            # Получаем заголовки с авторизацией
            headers = self._get_headers()
            
            # Для POST запросов с формой нужно установить Content-Type: application/x-www-form-urlencoded
            # и удалить Accept если он добавлен методом _get_headers
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            headers.pop('Accept', None)
            
            # Подготавливаем данные для запроса
            data = {
                'id': site_id
            }
            
            url = f"{self.API_URL}/delete.site"
            self.logger.debug(f"Отправка запроса на удаление сайта: {url}")
            self.logger.debug(f"Параметры запроса: {data}")
            self.logger.debug(f"Заголовки запроса: {headers}")
            
            # Выполняем POST запрос согласно документации API
            response = requests.post(url, headers=headers, data=data)
            
            self.logger.debug(f"Получен ответ от FFPanel: {response.status_code}")
            self.logger.debug(f"Заголовки ответа: {response.headers}")
            self.logger.debug(f"Текст ответа: {response.text}")
            
            # Пытаемся разобрать JSON ответ
            try:
                result = response.json()
                self.logger.debug(f"Получены данные: {result}")
            except ValueError:
                self.logger.error(f"Ошибка при разборе JSON-ответа: {response.text[:200]}...")
                return {
                    'success': False,
                    'message': f"Ошибка при разборе ответа: {response.text[:100]}..."
                }
            
            # Проверяем код ответа и код в теле ответа (может отличаться)
            response_code = result.get('code', 0)
            
            if response.status_code == 200 and (response_code == 200 or response_code == 0):
                self.logger.info(f"Сайт с ID {site_id} успешно удален из FFPanel")
                return {
                    'success': True,
                    'message': 'Сайт успешно удален'
                }
            else:
                error_message = result.get('message', 'Неизвестная ошибка')
                self.logger.error(f"Ошибка удаления сайта: {error_message}, HTTP код: {response.status_code}, API код: {response_code}")
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