from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import db, Dataset, DataItem
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def index():
    # ── Total data milik user ─────────────────────────────────
    total_data = DataItem.query\
        .join(Dataset)\
        .filter(Dataset.user_id == current_user.id)\
        .count()

    # ── Hitung per label ──────────────────────────────────────
    label_counts = db.session.query(
        DataItem.label,
        func.count(DataItem.id).label('jumlah')
    ).join(Dataset)\
     .filter(Dataset.user_id == current_user.id)\
     .group_by(DataItem.label)\
     .all()

    # Jadikan dict { 'positif': N, 'negatif': N, 'netral': N }
    counts = {row.label: row.jumlah for row in label_counts if row.label}
    positif = counts.get('positif', 0)
    negatif = counts.get('negatif', 0)
    netral  = counts.get('netral',  0)

    # ── Persentase ────────────────────────────────────────────
    pct_positif = round(positif / total_data * 100, 1) if total_data > 0 else 0
    pct_negatif = round(negatif / total_data * 100, 1) if total_data > 0 else 0
    pct_netral  = round(netral  / total_data * 100, 1) if total_data > 0 else 0

    # ── Data sudah dipreprocessing ────────────────────────────
    total_preprocessed = DataItem.query\
        .join(Dataset)\
        .filter(Dataset.user_id == current_user.id,
                DataItem.is_preprocessed == True)\
        .count()

    # ── Data per dataset (untuk chart bar) ───────────────────
    datasets_chart = db.session.query(
        Dataset.nama,
        func.sum(func.IF(DataItem.label == 'positif', 1, 0)).label('positif'),
        func.sum(func.IF(DataItem.label == 'negatif', 1, 0)).label('negatif'),
        func.sum(func.IF(DataItem.label == 'netral',  1, 0)).label('netral'),
    ).join(DataItem)\
     .filter(Dataset.user_id == current_user.id)\
     .group_by(Dataset.id, Dataset.nama)\
     .order_by(Dataset.created_at.asc())\
     .all()

    chart_labels   = [d.nama[:20] for d in datasets_chart]  # potong kalau panjang
    chart_positif  = [int(d.positif or 0) for d in datasets_chart]
    chart_negatif  = [int(d.negatif or 0) for d in datasets_chart]
    chart_netral   = [int(d.netral  or 0) for d in datasets_chart]

    stats = {
        'total_data'        : total_data,
        'positif'           : positif,
        'negatif'           : negatif,
        'netral'            : netral,
        'pct_positif'       : pct_positif,
        'pct_negatif'       : pct_negatif,
        'pct_netral'        : pct_netral,
        'total_preprocessed': total_preprocessed,
        'total_datasets'    : len(datasets_chart),
        # Chart
        'chart_labels'      : chart_labels,
        'chart_positif'     : chart_positif,
        'chart_negatif'     : chart_negatif,
        'chart_netral'      : chart_netral,
    }

    return render_template('dashboard.html', stats=stats)