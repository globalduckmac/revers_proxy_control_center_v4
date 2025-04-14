#!/usr/bin/env python3
"""
Скрипт для проверки и активации интеграции с FFPanel для определенного домена.
Позволяет включить FFPanel для домена и синхронизировать его, даже если это не выполняется через веб-интерфейс.

Запуск:
python domain_ffpanel_check.py <domain_id>

Дополнительные аргументы:
--enable - Включить интеграцию с FFPanel для домена
--sync - Синхронизировать домен с FFPanel
--verbose - Вывести подробную информацию
--list - Вывести список доменов и их идентификаторы
"""

import sys
import json
import time
import argparse
import requests
from datetime import datetime

from app import app, db
from models import Domain, SystemSetting
from modules.ffpanel_api import FFPanelAPI
from modules.domain_manager import DomainManager


def check_domain_ffpanel_status(domain_id):
    """
    Проверяет текущий статус FFPanel интеграции для домена.
    
    Args:
        domain_id (int): ID домена
        
    Returns:
        dict: Словарь с информацией о статусе домена в FFPanel
    """
    try:
        with app.app_context():
            domain = Domain.query.get(domain_id)
            if not domain:
                print(f"[!] Ошибка: Домен с ID {domain_id} не найден")
                return None
            
            print(f"=== Проверка домена {domain.name} (ID: {domain_id}) ===")
            print(f"FFPanel включен: {'Да' if domain.ffpanel_enabled else 'Нет'}")
            print(f"FFPanel ID: {domain.ffpanel_id or 'Не установлен'}")
            print(f"Статус: {domain.ffpanel_status or 'Не синхронизирован'}")
            
            # Получаем информацию о домене в FFPanel, если есть ID
            if domain.ffpanel_id:
                try:
                    # Инициализация FFPanelAPI
                    setting = SystemSetting.query.filter_by(key='ffpanel_token').first()
                    if not setting or not setting.value:
                        print("[!] Ошибка: Токен FFPanel не найден в базе данных")
                        return None
                    
                    ffpanel_api = FFPanelAPI(setting.value)
                    
                    # Получение информации о домене
                    site_info = ffpanel_api.get_site(domain.ffpanel_id)
                    if site_info and 'data' in site_info:
                        site_data = site_info['data']
                        print("\nДанные из FFPanel:")
                        print(f"Домен: {site_data.get('domain')}")
                        print(f"Статус: {site_data.get('status')}")
                        print(f"Последнее обновление: {site_data.get('updated_at')}")
                        return site_data
                    else:
                        print("[!] Ошибка: Не удалось получить информацию о домене из FFPanel")
                except Exception as e:
                    print(f"[!] Ошибка при проверке домена в FFPanel: {str(e)}")
            
            return None
    except Exception as e:
        print(f"[!] Ошибка при проверке статуса домена: {str(e)}")
        return None


def enable_ffpanel_for_domain(domain_id):
    """
    Включает FFPanel интеграцию для домена.
    
    Args:
        domain_id (int): ID домена
        
    Returns:
        bool: True, если операция выполнена успешно, иначе False
    """
    try:
        with app.app_context():
            domain = Domain.query.get(domain_id)
            if not domain:
                print(f"[!] Ошибка: Домен с ID {domain_id} не найден")
                return False
            
            # Включаем FFPanel для домена
            domain.ffpanel_enabled = True
            db.session.commit()
            
            print(f"[✓] FFPanel успешно включен для домена {domain.name} (ID: {domain_id})")
            return True
    except Exception as e:
        print(f"[!] Ошибка при включении FFPanel для домена: {str(e)}")
        return False


def sync_domain_with_ffpanel(domain_id, verbose=False):
    """
    Синхронизирует домен с FFPanel.
    
    Args:
        domain_id (int): ID домена
        verbose (bool): Вывести подробную информацию
        
    Returns:
        bool: True, если операция выполнена успешно, иначе False
    """
    try:
        with app.app_context():
            domain = Domain.query.get(domain_id)
            if not domain:
                print(f"[!] Ошибка: Домен с ID {domain_id} не найден")
                return False
            
            # Проверяем, включен ли FFPanel для домена
            if not domain.ffpanel_enabled:
                print(f"[!] Предупреждение: FFPanel не включен для домена {domain.name}")
                enable = input("Хотите включить FFPanel для этого домена? (y/n): ")
                if enable.lower() == 'y':
                    domain.ffpanel_enabled = True
                    db.session.commit()
                    print(f"[✓] FFPanel включен для домена {domain.name}")
                else:
                    print("[!] Синхронизация отменена")
                    return False
            
            # Инициализация менеджера доменов для синхронизации
            try:
                # Инициализация FFPanelAPI
                setting = SystemSetting.query.filter_by(key='ffpanel_token').first()
                if not setting or not setting.value:
                    print("[!] Ошибка: Токен FFPanel не найден в базе данных")
                    return False
                
                ffpanel_api = FFPanelAPI(setting.value)
                domain_manager = DomainManager()
                
                # Синхронизация домена
                print(f"\n[*] Синхронизация домена {domain.name} с FFPanel...")
                
                if domain.ffpanel_id:
                    # Обновление существующего домена
                    result = domain_manager.update_domain_in_ffpanel(domain)
                    if result:
                        print(f"[✓] Домен {domain.name} успешно обновлен в FFPanel (ID: {domain.ffpanel_id})")
                        
                        if verbose:
                            # Получаем обновленную информацию
                            time.sleep(1)  # Даем API время на обработку изменений
                            site_info = ffpanel_api.get_site(domain.ffpanel_id)
                            if site_info and 'data' in site_info:
                                print("\nОбновленные данные в FFPanel:")
                                site_data = site_info['data']
                                print(json.dumps(site_data, indent=2, ensure_ascii=False))
                        
                        return True
                    else:
                        print(f"[!] Ошибка при обновлении домена {domain.name} в FFPanel")
                        return False
                else:
                    # Создание нового домена в FFPanel
                    result = domain_manager.create_domain_in_ffpanel(domain)
                    if result:
                        print(f"[✓] Домен {domain.name} успешно создан в FFPanel (ID: {domain.ffpanel_id})")
                        
                        if verbose:
                            # Получаем информацию о созданном домене
                            time.sleep(1)  # Даем API время на обработку изменений
                            site_info = ffpanel_api.get_site(domain.ffpanel_id)
                            if site_info and 'data' in site_info:
                                print("\nДанные созданного домена в FFPanel:")
                                site_data = site_info['data']
                                print(json.dumps(site_data, indent=2, ensure_ascii=False))
                        
                        return True
                    else:
                        print(f"[!] Ошибка при создании домена {domain.name} в FFPanel")
                        return False
            except Exception as e:
                print(f"[!] Ошибка при синхронизации домена с FFPanel: {str(e)}")
                return False
    except Exception as e:
        print(f"[!] Общая ошибка при синхронизации домена: {str(e)}")
        return False


def list_domains():
    """
    Выводит список доменов и их идентификаторы.
    
    Returns:
        list: Список доменов
    """
    try:
        with app.app_context():
            domains = Domain.query.order_by(Domain.name).all()
            
            print(f"=== Список доменов ({len(domains)}) ===")
            print("{:<5} {:<30} {:<10} {:<15} {:<20}".format("ID", "Домен", "FFPanel", "FFPanel ID", "Статус"))
            print("-" * 80)
            
            for domain in domains:
                ffpanel_status = domain.ffpanel_status or 'не синхронизирован'
                print("{:<5} {:<30} {:<10} {:<15} {:<20}".format(
                    domain.id, 
                    domain.name, 
                    "включен" if domain.ffpanel_enabled else "выключен",
                    str(domain.ffpanel_id or ""), 
                    ffpanel_status
                ))
            
            return domains
    except Exception as e:
        print(f"[!] Ошибка при получении списка доменов: {str(e)}")
        return []


def main():
    """
    Основная функция скрипта.
    """
    parser = argparse.ArgumentParser(description='Проверка и активация интеграции с FFPanel для домена')
    parser.add_argument('domain_id', type=int, nargs='?', help='ID домена для проверки')
    parser.add_argument('--enable', action='store_true', help='Включить FFPanel для домена')
    parser.add_argument('--sync', action='store_true', help='Синхронизировать домен с FFPanel')
    parser.add_argument('--verbose', action='store_true', help='Вывести подробную информацию')
    parser.add_argument('--list', action='store_true', help='Вывести список доменов')
    args = parser.parse_args()
    
    print("=== Утилита проверки интеграции с FFPanel ===")
    print(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Выводим список доменов
    if args.list:
        list_domains()
        return True
    
    # Проверяем, указан ли ID домена
    if not args.domain_id:
        print("[!] Ошибка: ID домена не указан")
        print("[i] Используйте --list для просмотра списка доменов")
        return False
    
    # Проверяем статус домена
    status = check_domain_ffpanel_status(args.domain_id)
    
    # Включаем FFPanel для домена, если указан флаг --enable
    if args.enable:
        enable_ffpanel_for_domain(args.domain_id)
    
    # Синхронизируем домен с FFPanel, если указан флаг --sync
    if args.sync:
        sync_domain_with_ffpanel(args.domain_id, args.verbose)
    
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)