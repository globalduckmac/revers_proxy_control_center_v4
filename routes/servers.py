import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from models import Server, ServerLog, db
from modules.server_manager import ServerManager

bp = Blueprint('servers', __name__, url_prefix='/servers')
logger = logging.getLogger(__name__)

@bp.route('/')
@login_required
def index():
    """Show list of servers."""
    servers = Server.query.all()
    return render_template('servers/index.html', servers=servers)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Handle server creation."""
    if request.method == 'POST':
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        ssh_user = request.form.get('ssh_user')
        ssh_port = request.form.get('ssh_port', 22, type=int)
        auth_method = request.form.get('auth_method')
        ssh_key = request.form.get('ssh_key') if auth_method == 'key' else None
        ssh_password = request.form.get('ssh_password') if auth_method == 'password' else None
        verify_connection = 'verify_connection' in request.form
        
        # Validate required fields
        if not name or not ip_address or not ssh_user:
            flash('All required fields must be filled', 'danger')
            return render_template('servers/create.html')
        
        # Validate authentication method
        if auth_method == 'key' and not ssh_key and verify_connection:
            flash('SSH key is required when using key authentication', 'danger')
            return render_template('servers/create.html')
        
        if auth_method == 'password' and not ssh_password and verify_connection:
            flash('SSH password is required when using password authentication', 'danger')
            return render_template('servers/create.html')
        
        # Create server
        server = Server(
            name=name,
            ip_address=ip_address,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            ssh_key=ssh_key,
            ssh_password=ssh_password,
            status='pending'
        )
        
        db.session.add(server)
        db.session.commit()
        
        # Check connectivity if requested
        if verify_connection:
            if ServerManager.check_connectivity(server):
                flash(f'Server {name} added successfully and connectivity verified', 'success')
            else:
                flash(f'Server {name} added but connectivity check failed', 'warning')
        else:
            flash(f'Server {name} added successfully', 'success')
        
        return redirect(url_for('servers.index'))
    
    return render_template('servers/create.html')

@bp.route('/<int:server_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(server_id):
    """Handle server editing."""
    server = Server.query.get_or_404(server_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        ip_address = request.form.get('ip_address')
        ssh_user = request.form.get('ssh_user')
        ssh_port = request.form.get('ssh_port', 22, type=int)
        auth_method = request.form.get('auth_method')
        ssh_key = request.form.get('ssh_key') if auth_method == 'key' else None
        ssh_password = request.form.get('ssh_password') if auth_method == 'password' else None
        verify_connection = 'verify_connection' in request.form
        
        # Update server information
        server.name = name
        server.ip_address = ip_address
        server.ssh_user = ssh_user
        server.ssh_port = ssh_port
        
        # Update authentication based on method
        if auth_method == 'key':
            if ssh_key:  # Only update if provided (otherwise keep existing)
                server.ssh_key = ssh_key
            server.ssh_password = None
        else:
            if ssh_password:  # Only update if provided
                server.ssh_password = ssh_password
            server.ssh_key = None
        
        db.session.commit()
        
        # Check connectivity if requested
        if verify_connection:
            if ServerManager.check_connectivity(server):
                flash(f'Server {name} updated successfully and connectivity verified', 'success')
            else:
                flash(f'Server {name} updated but connectivity check failed', 'warning')
        else:
            flash(f'Server {name} updated successfully', 'success')
        
        return redirect(url_for('servers.index'))
    
    # Get server logs for display
    logs = ServerLog.query.filter_by(server_id=server_id).order_by(ServerLog.created_at.desc()).limit(20).all()
    
    return render_template('servers/edit.html', server=server, logs=logs)

@bp.route('/<int:server_id>/delete', methods=['POST'])
@login_required
def delete(server_id):
    """Handle server deletion."""
    server = Server.query.get_or_404(server_id)
    
    # Check if server has associated domain groups
    if server.domain_groups:
        flash(f'Cannot delete server {server.name} because it has associated domain groups. Remove these associations first.', 'danger')
        return redirect(url_for('servers.index'))
    
    # Delete server logs
    ServerLog.query.filter_by(server_id=server_id).delete()
    
    # Delete server
    db.session.delete(server)
    db.session.commit()
    
    flash(f'Server {server.name} deleted successfully', 'success')
    return redirect(url_for('servers.index'))

@bp.route('/<int:server_id>/check', methods=['GET'])
@login_required
def check_connectivity(server_id):
    """Check server connectivity."""
    server = Server.query.get_or_404(server_id)
    
    if ServerManager.check_connectivity(server):
        flash(f'Connectivity check successful for server {server.name}', 'success')
    else:
        flash(f'Connectivity check failed for server {server.name}', 'danger')
    
    return redirect(url_for('servers.index'))
