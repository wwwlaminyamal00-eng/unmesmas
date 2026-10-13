from flask import Blueprint, render_template

herramientas_bp = Blueprint('herramientas', __name__)

@herramientas_bp.route('/herramientas')
def herramientas():
    return render_template('herramientas.html')
