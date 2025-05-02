from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import Server, Domain, db

bp = Blueprint('websockets', __name__)

@bp.route('/status')
@login_required
def websocket_status():
    """Return WebSocket status."""
    return jsonify({
        'status': 'active',
        'message': 'WebSocket server is running'
    })
