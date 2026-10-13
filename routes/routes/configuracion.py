from flask import Blueprint, render_template

configuracion_bp = Blueprint('configuracion', __name__)

@configuracion_bp.route('/configuracion')
def configuracion():
    return render_template('configuracion.html')
