import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from models import Domain, DomainGroup, db

bp = Blueprint('domains', __name__, url_prefix='/domains')
logger = logging.getLogger(__name__)

@bp.route('/')
@login_required
def index():
    """Show list of domains."""
    # Получаем параметр группы из запроса
    group_id = request.args.get('group_id', type=int)
    
    # Получаем все группы доменов для фильтра
    domain_groups = DomainGroup.query.all()
    
    if group_id:
        # Если указана группа, фильтруем домены по этой группе
        group = DomainGroup.query.get_or_404(group_id)
        domains = group.domains.all()
    else:
        # Иначе показываем все домены
        domains = Domain.query.all()
    
    return render_template('domains/index.html', 
                          domains=domains, 
                          domain_groups=domain_groups,
                          selected_group_id=group_id)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Handle domain creation."""
    if request.method == 'POST':
        name = request.form.get('name')
        target_ip = request.form.get('target_ip')
        target_port = request.form.get('target_port', 80, type=int)
        ssl_enabled = 'ssl_enabled' in request.form
        
        # Validate required fields
        if not name or not target_ip:
            flash('Domain name and target IP are required', 'danger')
            return redirect(url_for('domains.create'))
        
        # Check if domain already exists
        existing_domain = Domain.query.filter_by(name=name).first()
        if existing_domain:
            flash(f'Domain {name} already exists', 'danger')
            return redirect(url_for('domains.create'))
        
        # Create domain
        domain = Domain(
            name=name,
            target_ip=target_ip,
            target_port=target_port,
            ssl_enabled=ssl_enabled
        )
        
        db.session.add(domain)
        db.session.commit()
        
        # Add to domain groups if specified
        group_ids = request.form.getlist('groups[]')
        if group_ids:
            for group_id in group_ids:
                group = DomainGroup.query.get(group_id)
                if group:
                    group.domains.append(domain)
            
            db.session.commit()
            flash(f'Domain {name} created and added to {len(group_ids)} group(s)', 'success')
        else:
            flash(f'Domain {name} created successfully', 'success')
        
        return redirect(url_for('domains.index'))
    
    # Get all domain groups for dropdown
    domain_groups = DomainGroup.query.all()
    
    return render_template('domains/create.html', domain_groups=domain_groups)

@bp.route('/<int:domain_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(domain_id):
    """Handle domain editing."""
    domain = Domain.query.get_or_404(domain_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        target_ip = request.form.get('target_ip')
        target_port = request.form.get('target_port', 80, type=int)
        ssl_enabled = 'ssl_enabled' in request.form
        
        # Validate required fields
        if not name or not target_ip:
            flash('Domain name and target IP are required', 'danger')
            return redirect(url_for('domains.edit', domain_id=domain_id))
        
        # Check if domain name changed and if new name already exists
        if name != domain.name:
            existing_domain = Domain.query.filter_by(name=name).first()
            if existing_domain:
                flash(f'Domain {name} already exists', 'danger')
                return redirect(url_for('domains.edit', domain_id=domain_id))
        
        # Update domain
        domain.name = name
        domain.target_ip = target_ip
        domain.target_port = target_port
        domain.ssl_enabled = ssl_enabled
        
        # Update domain groups
        domain.groups = []
        group_ids = request.form.getlist('groups[]')
        if group_ids:
            for group_id in group_ids:
                group = DomainGroup.query.get(group_id)
                if group:
                    domain.groups.append(group)
        
        db.session.commit()
        flash(f'Domain {name} updated successfully', 'success')
        
        return redirect(url_for('domains.index'))
    
    # Get all domain groups for dropdown
    domain_groups = DomainGroup.query.all()
    
    return render_template('domains/edit.html', domain=domain, domain_groups=domain_groups)

@bp.route('/<int:domain_id>/delete', methods=['POST'])
@login_required
def delete(domain_id):
    """Handle domain deletion."""
    domain = Domain.query.get_or_404(domain_id)
    name = domain.name
    
    # Remove domain from all groups
    domain.groups = []
    
    # Delete domain
    db.session.delete(domain)
    db.session.commit()
    
    flash(f'Domain {name} deleted successfully', 'success')
    return redirect(url_for('domains.index'))
