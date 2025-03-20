import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from models import DomainGroup, Server, Domain, db

bp = Blueprint('domain_groups', __name__, url_prefix='/domain-groups')
logger = logging.getLogger(__name__)

@bp.route('/')
@login_required
def index():
    """Show list of domain groups."""
    domain_groups = DomainGroup.query.all()
    return render_template('domain_groups/index.html', domain_groups=domain_groups)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Handle domain group creation."""
    if request.method == 'POST':
        name = request.form.get('name')
        server_id = request.form.get('server_id', type=int)
        
        # Validate required fields
        if not name:
            flash('Group name is required', 'danger')
            return redirect(url_for('domain_groups.create'))
        
        # Check if server exists if server_id provided
        if server_id:
            server = Server.query.get(server_id)
            if not server:
                flash(f'Server with ID {server_id} not found', 'danger')
                return redirect(url_for('domain_groups.create'))
        
        # Create domain group
        domain_group = DomainGroup(
            name=name,
            server_id=server_id
        )
        
        db.session.add(domain_group)
        db.session.commit()
        
        # Add domains to group if specified
        domain_ids = request.form.getlist('domains[]')
        if domain_ids:
            for domain_id in domain_ids:
                domain = Domain.query.get(domain_id)
                if domain:
                    domain_group.domains.append(domain)
            
            db.session.commit()
            flash(f'Domain group {name} created with {len(domain_ids)} domain(s)', 'success')
        else:
            flash(f'Domain group {name} created successfully', 'success')
        
        return redirect(url_for('domain_groups.index'))
    
    # Get all servers and domains for dropdowns
    servers = Server.query.all()
    domains = Domain.query.all()
    
    return render_template('domain_groups/create.html', servers=servers, domains=domains)

@bp.route('/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(group_id):
    """Handle domain group editing."""
    domain_group = DomainGroup.query.get_or_404(group_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        server_id = request.form.get('server_id', type=int)
        
        # Validate required fields
        if not name:
            flash('Group name is required', 'danger')
            return redirect(url_for('domain_groups.edit', group_id=group_id))
        
        # Update domain group
        domain_group.name = name
        domain_group.server_id = server_id
        
        # Update domains in group
        domain_group.domains = []
        domain_ids = request.form.getlist('domains[]')
        if domain_ids:
            for domain_id in domain_ids:
                domain = Domain.query.get(domain_id)
                if domain:
                    domain_group.domains.append(domain)
        
        db.session.commit()
        flash(f'Domain group {name} updated successfully', 'success')
        
        return redirect(url_for('domain_groups.index'))
    
    # Get all servers and domains for dropdowns
    servers = Server.query.all()
    domains = Domain.query.all()
    
    return render_template('domain_groups/edit.html', 
                          domain_group=domain_group, 
                          servers=servers, 
                          domains=domains)

@bp.route('/<int:group_id>/delete', methods=['POST'])
@login_required
def delete(group_id):
    """Handle domain group deletion."""
    domain_group = DomainGroup.query.get_or_404(group_id)
    name = domain_group.name
    
    # Remove all domains from group
    domain_group.domains = []
    
    # Delete domain group
    db.session.delete(domain_group)
    db.session.commit()
    
    flash(f'Domain group {name} deleted successfully', 'success')
    return redirect(url_for('domain_groups.index'))
