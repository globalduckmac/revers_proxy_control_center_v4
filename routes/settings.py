from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user

from app import db
from models import SystemSetting

bp = Blueprint('settings', __name__, url_prefix='/settings')

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
    
    return render_template('settings/index.html', settings=settings_list)

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
        if form_key in request.form:
            value = request.form[form_key].strip()
            
            # Если значение пустое, устанавливаем его в None
            if not value:
                value = None
            
            # Устанавливаем новое значение с учетом шифрования
            if value is not None or value != setting.get_value(key):
                SystemSetting.set_value(key, value, setting.description, setting.is_encrypted)
    
    db.session.commit()
    flash('Настройки системы успешно обновлены', 'success')
    
    return redirect(url_for('settings.index'))