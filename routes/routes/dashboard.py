from flask import Blueprint, redirect, url_for

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
def dashboard():
    # No existe templates/dashboard.html: el panel principal es /index
    return redirect(url_for('index'))
