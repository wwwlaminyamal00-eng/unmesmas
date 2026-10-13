from flask import Blueprint, render_template

reportes_bp = Blueprint('reportes', __name__)

@reportes_bp.route('/reportes')
def reportes():
    return render_template('reportes.html')
