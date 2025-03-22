from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import SystemSetting, db
from app import app
import os

bp = Blueprint('settings', __name__, url_prefix='/settings')

@bp.route('/', methods=['GET'])
@login_required
def index():
    """Отображает страницу с системными настройками."""
    # Проверка, что пользователь является администратором
    if not current_user.is_admin:
        flash('Доступ запрещен. Требуются права администратора.', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    # Получение всех настроек из базы данных
    settings = SystemSetting.query.all()
    
    # Предварительно заданные настройки с описаниями
    predefined_settings = {
        'telegram_bot_token': {
            'description': 'Токен бота Telegram для отправки уведомлений',
            'is_encrypted': True
        },
        'telegram_chat_id': {
            'description': 'ID чата Telegram для отправки уведомлений',
            'is_encrypted': False
        },
        'ffpanel_token': {
            'description': 'Токен для взаимодействия с FFPanel API',
            'is_encrypted': True
        },
        'github_token': {
            'description': 'Токен доступа к GitHub API (для возможности автоматического обновления)',
            'is_encrypted': True
        }
    }
    
    # Создание недостающих настроек в базе данных
    for key, config in predefined_settings.items():
        setting = SystemSetting.query.filter_by(key=key).first()
        if not setting:
            # Проверяем, есть ли значение в переменных окружения
            env_value = os.environ.get(key.upper(), None)
            SystemSetting.set_value(
                key=key,
                value=env_value,
                description=config['description'],
                is_encrypted=config['is_encrypted']
            )
    
    # Получаем обновленный список настроек
    settings = SystemSetting.query.all()
    return render_template('settings/index.html', settings=settings)

@bp.route('/update', methods=['POST'])
@login_required
def update():
    """Обрабатывает обновление системных настроек."""
    # Проверка, что пользователь является администратором
    if not current_user.is_admin:
        flash('Доступ запрещен. Требуются права администратора.', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    # Обработка формы
    for key, value in request.form.items():
        if key.startswith('setting_'):
            setting_key = key.replace('setting_', '')
            setting = SystemSetting.query.filter_by(key=setting_key).first()
            
            if setting:
                # Проверяем, нужно ли шифровать значение
                current_value = setting.get_value(setting_key)
                
                # Обновляем значение только если оно изменилось
                if value != current_value and value.strip():
                    SystemSetting.set_value(
                        key=setting_key,
                        value=value,
                        is_encrypted=setting.is_encrypted
                    )
    
    # Сохранение настроек в переменные окружения (опционально)
    # Это обеспечит их доступность для всех компонентов системы
    for setting in SystemSetting.query.all():
        env_var_name = setting.key.upper()
        value = setting.get_value(setting.key)
        if value:
            os.environ[env_var_name] = value
    
    flash('Настройки успешно обновлены.', 'success')
    return redirect(url_for('settings.index'))