#!/usr/bin/env python3

from app import app
from models import Domain

def list_domains():
    with app.app_context():
        print('Список первых 5 доменов из базы данных:')
        domains = Domain.query.limit(5).all()
        
        for d in domains:
            ffpanel_status = d.ffpanel_status or 'не синхронизирован'
            print(f'ID: {d.id}, Имя: {d.name}, FFPanel: {"включен" if d.ffpanel_enabled else "выключен"}, FFPanel ID: {d.ffpanel_id or "не установлен"}, Статус: {ffpanel_status}')
        
        print("\nОбновление флага ffpanel_enabled для первых 5 доменов...")
        for d in domains:
            print(f"Обновление домена {d.name} (ID: {d.id})...")
            d.ffpanel_enabled = True
            # Сохраняем изменения
        from app import db
        db.session.commit()
        print("Обновление завершено!")

if __name__ == "__main__":
    list_domains()