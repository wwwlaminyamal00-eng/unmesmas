from flask import Blueprint, render_template

papelera_bp = Blueprint('papelera', __name__)

@papelera_bp.route('/papelera')
def papelera():
    return render_template('papelera.html')
