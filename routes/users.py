from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from models import User

bp = Blueprint('users', __name__, url_prefix='/users')

@bp.route('/')
@login_required
def index():
    """Отображает список пользователей."""
    # Только администраторы могут просматривать список пользователей
    if not current_user.is_admin:
        flash('У вас нет прав для доступа к этой странице', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    users = User.query.order_by(User.username).all()
    return render_template('users/index.html', users=users)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создание нового пользователя."""
    # Только администраторы могут создавать пользователей
    if not current_user.is_admin:
        flash('У вас нет прав для создания пользователей', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = 'is_admin' in request.form
        
        # Валидация полей
        if not username or not email or not password:
            flash('Все поля обязательны для заполнения', 'danger')
            return render_template('users/create.html')
        
        # Проверка уникальности имени пользователя
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash(f'Пользователь с именем {username} уже существует', 'danger')
            return render_template('users/create.html')
        
        # Проверка уникальности email
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash(f'Пользователь с email {email} уже существует', 'danger')
            return render_template('users/create.html')
        
        # Создание нового пользователя
        new_user = User(
            username=username,
            email=email,
            is_admin=is_admin
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash(f'Пользователь {username} успешно создан', 'success')
        return redirect(url_for('users.index'))
    
    return render_template('users/create.html')

@bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(user_id):
    """Редактирование пользователя."""
    # Только администраторы могут редактировать пользователей
    if not current_user.is_admin:
        flash('У вас нет прав для редактирования пользователей', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Предотвращаем редактирование собственной учетной записи через этот интерфейс
    if user.id == current_user.id:
        flash('Редактирование собственной учетной записи недоступно через данный интерфейс', 'warning')
        return redirect(url_for('users.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = 'is_admin' in request.form
        
        # Валидация полей
        if not username or not email:
            flash('Имя пользователя и email обязательны для заполнения', 'danger')
            return render_template('users/edit.html', user=user)
        
        # Проверка уникальности имени пользователя
        if username != user.username:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash(f'Пользователь с именем {username} уже существует', 'danger')
                return render_template('users/edit.html', user=user)
        
        # Проверка уникальности email
        if email != user.email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash(f'Пользователь с email {email} уже существует', 'danger')
                return render_template('users/edit.html', user=user)
        
        # Обновление данных пользователя
        user.username = username
        user.email = email
        user.is_admin = is_admin
        
        # Обновление пароля только если он был предоставлен
        if password:
            user.set_password(password)
        
        db.session.commit()
        
        flash(f'Пользователь {username} успешно обновлен', 'success')
        return redirect(url_for('users.index'))
    
    return render_template('users/edit.html', user=user)

@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Изменение собственного пароля пользователя."""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Валидация полей
        if not current_password or not new_password or not confirm_password:
            flash('Все поля обязательны для заполнения', 'danger')
            return render_template('users/change_password.html')
        
        # Проверка текущего пароля
        if not current_user.check_password(current_password):
            flash('Текущий пароль введен неверно', 'danger')
            return render_template('users/change_password.html')
        
        # Проверка совпадения нового пароля и подтверждения
        if new_password != confirm_password:
            flash('Новый пароль и подтверждение не совпадают', 'danger')
            return render_template('users/change_password.html')
        
        # Проверка сложности пароля (минимум 8 символов)
        if len(new_password) < 8:
            flash('Новый пароль должен содержать минимум 8 символов', 'danger')
            return render_template('users/change_password.html')
        
        # Установка нового пароля
        current_user.set_password(new_password)
        db.session.commit()
        
        flash('Ваш пароль успешно изменен', 'success')
        return redirect(url_for('auth.dashboard'))
    
    return render_template('users/change_password.html')

@bp.route('/<int:user_id>/delete', methods=['POST'])
@login_required
def delete(user_id):
    """Удаление пользователя."""
    # Только администраторы могут удалять пользователей
    if not current_user.is_admin:
        flash('У вас нет прав для удаления пользователей', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Предотвращаем удаление собственной учетной записи
    if user.id == current_user.id:
        flash('Удаление собственной учетной записи недопустимо', 'danger')
        return redirect(url_for('users.index'))
    
    # Предотвращаем удаление последнего администратора
    if user.is_admin:
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            flash('Невозможно удалить последнего администратора в системе', 'danger')
            return redirect(url_for('users.index'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Пользователь {username} успешно удален', 'success')
    return redirect(url_for('users.index'))