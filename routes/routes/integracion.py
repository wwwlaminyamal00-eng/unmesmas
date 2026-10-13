from flask import Blueprint, render_template

integracion_bp = Blueprint('integracion', __name__)

@integracion_bp.route('/integracion')
def integracion():
    return render_template('integracion.html')
