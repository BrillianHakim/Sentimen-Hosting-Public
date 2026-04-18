from flask import Blueprint, render_template
from flask_login import login_required, current_user

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Data dummy — nanti diganti data real dari DB
    stats = {
        'total_data'    : 1240,
        'positif'       : 850,
        'negatif'       : 390,
        'akurasi'       : 92.5,
        'pct_positif'   : 68.5,
        'pct_negatif'   : 31.5,
    }
    return render_template('dashboard.html', stats=stats)