import os
import subprocess
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app as app
from flask_login import login_required, current_user

from app import db
from models import SystemSetting

bp = Blueprint('settings', __name__, url_prefix='/settings')

def get_git_version():
    """
    Получает информацию о текущей версии приложения из git.
    
    Returns:
        dict: Словарь с информацией о версии
            - version: текущая версия (хеш коммита)
            - branch: текущая ветка
            - last_commit: информация о последнем коммите
    """
    try:
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Получаем текущую ветку
        process = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        branch = process.stdout.strip() if process.returncode == 0 else "Unknown"
        
        # Получаем хеш последнего коммита
        process = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        version = process.stdout.strip() if process.returncode == 0 else "Unknown"
        
        # Получаем информацию о последнем коммите
        process = subprocess.run(
            ['git', 'log', '-1', '--pretty=format:%an - %s (%ad)', '--date=short'],
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        last_commit = process.stdout.strip() if process.returncode == 0 else "Unknown"
        
        return {
            'version': version,
            'branch': branch,
            'last_commit': last_commit
        }
    except Exception as e:
        return {
            'version': 'Unknown',
            'branch': 'Unknown',
            'last_commit': f'Error: {str(e)}'
        }

@bp.route('/')
@login_required
def index():
    """Отображает страницу с системными настройками."""
    # Только администраторы могут изменять настройки
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к настройкам системы', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    # Получаем все настройки из базы данных
    settings_list = SystemSetting.query.order_by(SystemSetting.key).all()
    
    # Проверяем наличие обязательных настроек и создаем их, если они отсутствуют
    required_settings = {
        'telegram_bot_token': ('Токен бота Telegram', True),
        'telegram_chat_id': ('ID чата Telegram для уведомлений', False),
        'ffpanel_token': ('Токен API FFPanel', True)
    }
    
    # Создаем отсутствующие настройки
    existing_keys = {setting.key for setting in settings_list}
    for key, (description, is_encrypted) in required_settings.items():
        if key not in existing_keys:
            new_setting = SystemSetting(
                key=key,
                description=description,
                is_encrypted=is_encrypted
            )
            db.session.add(new_setting)
            settings_list.append(new_setting)
    
    db.session.commit()
    
    # Получаем информацию о версии
    version_info = get_git_version()
    
    return render_template('settings/index.html', settings=settings_list, version_info=version_info)

@bp.route('/update', methods=['POST'])
@login_required
def update():
    """Обрабатывает обновление системных настроек."""
    # Только администраторы могут изменять настройки
    if not current_user.is_admin:
        flash('У вас нет прав для изменения настроек системы', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    # Получаем все настройки из базы данных
    all_settings = SystemSetting.query.all()
    settings_dict = {setting.key: setting for setting in all_settings}
    
    # Обновляем значения настроек из формы
    for key, setting in settings_dict.items():
        form_key = f'setting_{key}'
        has_value_key = f'has_value_{key}'
        
        # Для зашифрованных полей особая логика
        if setting.is_encrypted:
            value = request.form.get(form_key, '').strip()
            has_existing_value = request.form.get(has_value_key) == "1"
            
            # Если поле пустое, но было ранее заполнено - сохраняем старое значение
            if not value and has_existing_value:
                continue  # Пропускаем обновление, сохраняем старое значение
            
            # Если поле заполнено - обновляем значение
            if value:
                SystemSetting.set_value(key, value, setting.description, setting.is_encrypted)
                # Добавляем отладочный вывод для FFPanel токена 
                if key == 'ffpanel_token':
                    app.logger.info(f"FFPanel токен обновлен, длина: {len(value)}")
        else:
            # Для обычных полей стандартная логика
            if form_key in request.form:
                value = request.form[form_key].strip()
                
                # Если значение пустое, устанавливаем его в None
                if not value:
                    value = None
                
                # Устанавливаем новое значение
                SystemSetting.set_value(key, value, setting.description, setting.is_encrypted)
    
    db.session.commit()
    flash('Настройки системы успешно обновлены', 'success')
    
    return redirect(url_for('settings.index'))

@bp.route('/update-app', methods=['POST'])
@login_required
def update_app():
    """Обновляет приложение из GitHub (git pull)."""
    # Только администраторы могут обновлять приложение
    if not current_user.is_admin:
        flash('У вас нет прав для обновления приложения', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    restart_requested = request.form.get('restart', 'false') == 'true'
    service_name = request.form.get('service_name', '').strip()
    
    try:
        # Получаем корневую директорию приложения
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Выполняем git pull в директории приложения
        process = subprocess.run(
            ['git', 'pull', 'origin', 'pre_agent'],
            cwd=app_root,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Проверяем результат выполнения команды
        if process.returncode == 0:
            # Успешное обновление
            output = process.stdout.strip()
            has_updates = "Already up to date" not in output
            
            if has_updates:
                if restart_requested and service_name:
                    try:
                        # Перезапускаем systemd сервис
                        restart_process = subprocess.run(
                            ['sudo', 'systemctl', 'restart', service_name],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        
                        if restart_process.returncode == 0:
                            flash(f'Приложение успешно обновлено и сервис {service_name} перезапущен.<br><pre>{output}</pre>', 'success')
                        else:
                            error_msg = restart_process.stderr.strip() or "Неизвестная ошибка"
                            flash(f'Приложение обновлено, но перезапуск сервиса не удался: {error_msg}<br><pre>{output}</pre>', 'warning')
                    except Exception as restart_error:
                        flash(f'Приложение обновлено, но перезапуск сервиса не удался: {str(restart_error)}<br><pre>{output}</pre>', 'warning')
                else:
                    flash(f'Приложение успешно обновлено. Для применения изменений перезапустите сервер.<br><pre>{output}</pre>', 'success')
            else:
                flash('Приложение уже обновлено до последней версии', 'info')
        else:
            # Ошибка при обновлении
            flash(f'Ошибка при обновлении приложения:<br><pre>{process.stderr}</pre>', 'danger')
    
    except Exception as e:
        flash(f'Возникла ошибка при обновлении приложения: {str(e)}', 'danger')
    
    return redirect(url_for('settings.index'))