import os
import logging
from datetime import datetime, timedelta
import telegram
from telegram.error import TelegramError
from sqlalchemy import func, desc, and_
from app import db
from models import Server, Domain, DomainGroup, ServerMetric, DomainMetric, ServerLog, ServerGroup

# Настройка логирования
logger = logging.getLogger(__name__)

# Получаем токен бота и ID чата из переменных окружения
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Пороговые значения для уведомлений
CPU_THRESHOLD = 80  # % CPU
MEMORY_THRESHOLD = 80  # % памяти
DISK_THRESHOLD = 85  # % дискового пространства

class TelegramNotifier:
    """
    Класс для отправки уведомлений в Telegram
    """
    
    @staticmethod
    def is_configured():
        """
        Проверяет, настроены ли токен бота и ID чата
        
        Returns:
            bool: True, если настроены, иначе False
        """
        return TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
    
    @staticmethod
    async def send_message(text, parse_mode='HTML'):
        """
        Отправляет сообщение в Telegram
        
        Args:
            text (str): Текст сообщения
            parse_mode (str): Режим форматирования текста (HTML, Markdown)
            
        Returns:
            bool: True, если сообщение отправлено успешно, иначе False
        """
        if not TelegramNotifier.is_configured():
            logger.warning("Telegram notifications are not configured")
            return False
        
        try:
            bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=text,
                parse_mode=parse_mode
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send Telegram notification: {str(e)}")
            return False
    
    @staticmethod
    async def notify_server_status_change(server, old_status, new_status):
        """
        Отправляет уведомление об изменении статуса сервера
        
        Args:
            server (Server): Объект сервера
            old_status (str): Предыдущий статус
            new_status (str): Новый статус
        """
        emoji = "🔴" if new_status == 'error' else "🟢"
        
        # Получаем группы, в которые входит сервер
        groups_text = ""
        if server.groups:
            groups_text = "<b>Группы сервера:</b>\n"
            for group in server.groups:
                desc = f" - {group.description}" if group.description else ""
                groups_text += f"• <b>{group.name}</b>{desc}\n"
                
                # Получаем статус других серверов в этой группе
                other_servers = group.servers.filter(Server.id != server.id).all()
                if other_servers:
                    active_count = sum(1 for s in other_servers if s.status == 'active')
                    error_count = len(other_servers) - active_count
                    groups_text += f"  ✅ {active_count} активных, ❌ {error_count} недоступных серверов в группе\n"
        
        message = f"{emoji} <b>Изменение статуса сервера</b>\n\n" \
                  f"Сервер: <b>{server.name}</b>\n" \
                  f"IP: {server.ip_address}\n" \
                  f"Статус: {old_status} → <b>{new_status}</b>\n"
                  
        if groups_text:
            message += f"\n{groups_text}"
            
        message += f"Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await TelegramNotifier.send_message(message)
    
    @staticmethod
    async def notify_domain_ns_status_change(domain, old_status, new_status):
        """
        Отправляет уведомление об изменении статуса NS-записей домена
        
        Args:
            domain (Domain): Объект домена
            old_status (str): Предыдущий статус
            new_status (str): Новый статус
        """
        emoji = "🔴" if new_status == 'mismatch' else "🟢"
        
        # Получаем группы, в которые входит домен
        groups_text = "<b>Группы домена:</b>\n"
        domain_groups = list(domain.groups)
        
        if not domain_groups:
            groups_text += "Домен не входит ни в одну группу\n"
        else:
            for group in domain_groups:
                server_name = group.server.name if group.server else "Нет сервера"
                groups_text += f"• <b>{group.name}</b> (сервер: {server_name})\n"
                
                # Добавляем информацию о других доменах в группе
                other_domains = group.domains.filter(Domain.id != domain.id).all()
                if other_domains:
                    ok_count = sum(1 for d in other_domains if d.ns_status == 'ok')
                    error_count = sum(1 for d in other_domains if d.ns_status == 'mismatch')
                    pending_count = len(other_domains) - ok_count - error_count
                    
                    groups_text += f"  ✅ {ok_count} корректных, " \
                                   f"❌ {error_count} с ошибками, " \
                                   f"⏳ {pending_count} ожидающих доменов в группе\n"
        
        message = f"{emoji} <b>Изменение статуса NS-записей домена</b>\n\n" \
                  f"Домен: <b>{domain.name}</b>\n" \
                  f"Статус: {old_status} → <b>{new_status}</b>\n\n" \
                  f"{groups_text}\n" \
                  f"Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await TelegramNotifier.send_message(message)
    
    @staticmethod
    async def notify_server_high_load(server, metric):
        """
        Отправляет уведомление о высокой нагрузке на сервер
        
        Args:
            server (Server): Объект сервера
            metric (ServerMetric): Метрика сервера
        """
        alerts = []
        
        if metric.cpu_usage and metric.cpu_usage > CPU_THRESHOLD:
            alerts.append(f"CPU: {metric.cpu_usage:.1f}% (порог: {CPU_THRESHOLD}%)")
        
        if metric.memory_usage and metric.memory_usage > MEMORY_THRESHOLD:
            alerts.append(f"Память: {metric.memory_usage:.1f}% (порог: {MEMORY_THRESHOLD}%)")
        
        if metric.disk_usage and metric.disk_usage > DISK_THRESHOLD:
            alerts.append(f"Диск: {metric.disk_usage:.1f}% (порог: {DISK_THRESHOLD}%)")
        
        if not alerts:
            return  # Нет превышений порогов
        
        # Получаем группы, в которые входит сервер
        groups_text = ""
        if server.groups:
            groups_text = "<b>Группы сервера:</b>\n"
            for group in server.groups:
                desc = f" - {group.description}" if group.description else ""
                groups_text += f"• <b>{group.name}</b>{desc}\n"
                
                # Получаем статус других серверов в этой группе
                other_servers = group.servers.filter(Server.id != server.id).all()
                if other_servers:
                    active_count = sum(1 for s in other_servers if s.status == 'active')
                    error_count = len(other_servers) - active_count
                    groups_text += f"  ✅ {active_count} активных, ❌ {error_count} недоступных серверов в группе\n"
        
        message = f"⚠️ <b>Высокая нагрузка на сервер</b>\n\n" \
                  f"Сервер: <b>{server.name}</b>\n" \
                  f"IP: {server.ip_address}\n" \
                  f"Предупреждения:\n- " + "\n- ".join(alerts) + "\n"
                  
        if groups_text:
            message += f"\n{groups_text}"
            
        message += f"\nВремя: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await TelegramNotifier.send_message(message)
    
    @staticmethod
    async def send_daily_report():
        """
        Отправляет ежедневный отчет о состоянии системы
        """
        # Получаем данные за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Статусы серверов
        servers = Server.query.all()
        total_servers = len(servers)
        active_servers = sum(1 for s in servers if s.status == 'active')
        inactive_servers = total_servers - active_servers
        
        # Статусы доменов
        domains = Domain.query.filter(Domain.expected_nameservers.isnot(None)).all()
        total_domains = len(domains)
        ok_domains = sum(1 for d in domains if d.ns_status == 'ok')
        mismatch_domains = sum(1 for d in domains if d.ns_status == 'mismatch')
        pending_domains = total_domains - ok_domains - mismatch_domains
        
        # Данные по группам серверов
        server_groups = ServerGroup.query.all()
        server_groups_data = []
        
        for group in server_groups:
            servers_in_group = group.servers.all()
            total_in_group = len(servers_in_group)
            
            if total_in_group == 0:
                continue  # Пропускаем пустые группы
            
            active_in_group = sum(1 for s in servers_in_group if s.status == 'active')
            
            server_groups_data.append({
                'name': group.name,
                'description': group.description,
                'total': total_in_group,
                'active': active_in_group,
                'inactive': total_in_group - active_in_group
            })
        
        # Данные по группам доменов
        domain_groups = DomainGroup.query.all()
        groups_data = []
        
        for group in domain_groups:
            domains_in_group = group.domains.all()
            total_in_group = len(domains_in_group)
            
            if total_in_group == 0:
                continue  # Пропускаем пустые группы
            
            ok_in_group = sum(1 for d in domains_in_group if d.ns_status == 'ok')
            mismatch_in_group = sum(1 for d in domains_in_group if d.ns_status == 'mismatch')
            
            server_name = group.server.name if group.server else "Нет сервера"
            
            groups_data.append({
                'name': group.name,
                'server': server_name,
                'total': total_in_group,
                'ok': ok_in_group,
                'mismatch': mismatch_in_group
            })
        
        # Статистика по метрикам серверов
        server_metrics = {}
        for server in servers:
            if server.status != 'active':
                continue
                
            # Получаем метрики за последние 24 часа
            metrics = ServerMetric.query.filter(
                ServerMetric.server_id == server.id,
                ServerMetric.timestamp >= yesterday
            ).all()
            
            if not metrics:
                continue
                
            avg_cpu = sum(m.cpu_usage for m in metrics if m.cpu_usage) / len(metrics) if metrics else 0
            avg_memory = sum(m.memory_usage for m in metrics if m.memory_usage) / len(metrics) if metrics else 0
            avg_disk = sum(m.disk_usage for m in metrics if m.disk_usage) / len(metrics) if metrics else 0
            
            max_cpu = max((m.cpu_usage for m in metrics if m.cpu_usage), default=0)
            max_memory = max((m.memory_usage for m in metrics if m.memory_usage), default=0)
            max_disk = max((m.disk_usage for m in metrics if m.disk_usage), default=0)
            
            server_metrics[server.name] = {
                'avg_cpu': avg_cpu,
                'avg_memory': avg_memory,
                'avg_disk': avg_disk,
                'max_cpu': max_cpu,
                'max_memory': max_memory,
                'max_disk': max_disk
            }
        
        # Статистика по доменам с наибольшим трафиком
        from sqlalchemy import desc
        top_domains_by_traffic = db.session.query(
            Domain.name,
            func.sum(DomainMetric.bandwidth_used).label('total_bandwidth'),
            func.sum(DomainMetric.requests_count).label('total_requests')
        ).join(DomainMetric).filter(
            DomainMetric.timestamp >= yesterday
        ).group_by(Domain.name).order_by(
            desc('total_bandwidth')
        ).limit(5).all()
        
        # Формируем отчет
        report = f"📊 <b>Ежедневный отчет о состоянии системы</b>\n" \
                 f"<i>за период {yesterday.strftime('%Y-%m-%d %H:%M')} — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}</i>\n\n"
        
        # Состояние серверов
        report += f"<b>Серверы:</b> {active_servers}/{total_servers} активны\n"
        if inactive_servers > 0:
            report += "❌ <b>Недоступные серверы:</b>\n"
            for server in servers:
                if server.status != 'active':
                    report += f"- {server.name} ({server.ip_address})\n"
        report += "\n"
        
        # Состояние доменов
        report += f"<b>Домены:</b> {ok_domains}/{total_domains} работают корректно\n"
        if mismatch_domains > 0:
            report += f"⚠️ Несоответствие NS: {mismatch_domains}\n"
        if pending_domains > 0:
            report += f"⏳ Ожидают проверки: {pending_domains}\n"
        report += "\n"
        
        # Статистика по группам серверов
        if server_groups_data:
            report += "<b>Статистика по группам серверов:</b>\n"
            for group in server_groups_data:
                desc = f" - {group['description']}" if group['description'] else ""
                report += f"• <b>{group['name']}</b>{desc}\n" \
                        f"  ✅ {group['active']}/{group['total']} активны\n" \
                        f"  ❌ {group['inactive']}/{group['total']} недоступны\n"
            report += "\n"
        
        # Статистика по группам доменов
        if groups_data:
            report += "<b>Статистика по группам доменов:</b>\n"
            for group in groups_data:
                report += f"• <b>{group['name']}</b> (сервер: {group['server']})\n" \
                        f"  ✅ {group['ok']}/{group['total']} работают корректно\n" \
                        f"  ❌ {group['mismatch']}/{group['total']} с ошибками\n"
            report += "\n"
        
        # Нагрузка на серверы
        if server_metrics:
            report += "<b>Нагрузка на серверы за 24 часа:</b>\n"
            for server_name, metrics in server_metrics.items():
                report += f"• <b>{server_name}</b>\n" \
                        f"  CPU: ср. {metrics['avg_cpu']:.1f}%, макс. {metrics['max_cpu']:.1f}%\n" \
                        f"  Память: ср. {metrics['avg_memory']:.1f}%, макс. {metrics['max_memory']:.1f}%\n" \
                        f"  Диск: ср. {metrics['avg_disk']:.1f}%, макс. {metrics['max_disk']:.1f}%\n"
            report += "\n"
        
        # Убрали информацию о Топ-5 доменов по трафику по требованию клиента
        
        # Отправляем отчет
        await TelegramNotifier.send_message(report)