from app import db
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import ServerGroup, Server
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import NotFound

server_groups_bp = Blueprint('server_groups', __name__)


@server_groups_bp.route('/')
@login_required
def index():
    """Показывает список групп серверов."""
    groups = ServerGroup.query.all()
    return render_template('server_groups/index.html', groups=groups)


@server_groups_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Обрабатывает создание новой группы серверов."""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if not name:
            flash('Название группы серверов обязательно', 'danger')
            return redirect(url_for('server_groups.create'))
        
        # Создаем новую группу серверов
        group = ServerGroup(name=name, description=description)
        
        # Добавляем сервера в группу, если они были выбраны
        selected_servers = request.form.getlist('servers')
        if selected_servers:
            servers = Server.query.filter(Server.id.in_(selected_servers)).all()
            group.servers = servers
        
        try:
            db.session.add(group)
            db.session.commit()
            flash('Группа серверов успешно создана', 'success')
            return redirect(url_for('server_groups.index'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'Ошибка при создании группы серверов: {str(e)}', 'danger')
    
    # Для GET запроса или при ошибке POST
    servers = Server.query.all()
    return render_template('server_groups/create.html', servers=servers)


@server_groups_bp.route('/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(group_id):
    """Обрабатывает редактирование группы серверов."""
    group = ServerGroup.query.get_or_404(group_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if not name:
            flash('Название группы серверов обязательно', 'danger')
            return redirect(url_for('server_groups.edit', group_id=group_id))
        
        # Обновляем группу серверов
        group.name = name
        group.description = description
        
        # Обновляем список серверов в группе
        selected_servers = request.form.getlist('servers')
        if selected_servers:
            servers = Server.query.filter(Server.id.in_(selected_servers)).all()
            group.servers = servers
        else:
            group.servers = []
        
        try:
            db.session.commit()
            flash('Группа серверов успешно обновлена', 'success')
            return redirect(url_for('server_groups.index'))
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении группы серверов: {str(e)}', 'danger')
    
    # Для GET запроса или при ошибке POST
    servers = Server.query.all()
    return render_template('server_groups/edit.html', group=group, servers=servers)


@server_groups_bp.route('/<int:group_id>/delete', methods=['POST'])
@login_required
def delete(group_id):
    """Обрабатывает удаление группы серверов."""
    group = ServerGroup.query.get_or_404(group_id)
    
    try:
        db.session.delete(group)
        db.session.commit()
        flash('Группа серверов успешно удалена', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f'Ошибка при удалении группы серверов: {str(e)}', 'danger')
    
    return redirect(url_for('server_groups.index'))


@server_groups_bp.route('/<int:group_id>/servers')
@login_required
def servers(group_id):
    """Показывает список серверов в группе."""
    group = ServerGroup.query.get_or_404(group_id)
    return render_template('server_groups/servers.html', group=group)


@server_groups_bp.route('/<int:group_id>/add_server/<int:server_id>', methods=['POST'])
@login_required
def add_server(group_id, server_id):
    """Добавляет сервер в группу."""
    group = ServerGroup.query.get_or_404(group_id)
    server = Server.query.get_or_404(server_id)
    
    if server not in group.servers:
        group.servers.append(server)
        try:
            db.session.commit()
            flash(f'Сервер {server.name} добавлен в группу {group.name}', 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении сервера в группу: {str(e)}', 'danger')
    else:
        flash(f'Сервер {server.name} уже находится в группе {group.name}', 'warning')
    
    return redirect(url_for('server_groups.servers', group_id=group_id))


@server_groups_bp.route('/<int:group_id>/remove_server/<int:server_id>', methods=['POST'])
@login_required
def remove_server(group_id, server_id):
    """Удаляет сервер из группы."""
    group = ServerGroup.query.get_or_404(group_id)
    server = Server.query.get_or_404(server_id)
    
    if server in group.servers:
        group.servers.remove(server)
        try:
            db.session.commit()
            flash(f'Сервер {server.name} удален из группы {group.name}', 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f'Ошибка при удалении сервера из группы: {str(e)}', 'danger')
    else:
        flash(f'Сервер {server.name} не находится в группе {group.name}', 'warning')
    
    return redirect(url_for('server_groups.servers', group_id=group_id))