from flask import Blueprint, jsonify
from flask_login import login_required

bp = Blueprint('websockets', __name__)


@bp.route('/status')
@login_required
def websocket_status():
    """Return WebSocket status."""
    return jsonify({
        'status': 'active',
        'message': 'WebSocket server is running'
    })
