from flask import Blueprint, render_template, current_app
from flask_login import login_required, current_user
from models import db, Dataset, DataItem, HasilKlasifikasi
from sqlalchemy import func
from collections import Counter
import json, os, re

hasil_riset_bp = Blueprint('hasil_riset', __name__)


def _parse_metrics(text):
    m = {'akurasi': 0,
         'precision_pos': 0, 'recall_pos': 0, 'f1_pos': 0, 'support_pos': 0,
         'precision_neg': 0, 'recall_neg': 0, 'f1_neg': 0, 'support_neg': 0,
         'precision_neu': 0, 'recall_neu': 0, 'f1_neu': 0, 'support_neu': 0,
         'macro_f1': 0, 'weighted_f1': 0}
    if not text:
        return m
    try:
        for line in text.splitlines():
            line = line.strip()
            if 'Akurasi' in line or 'akurasi' in line:
                parts = line.split(':')
                if len(parts) > 1:
                    m['akurasi'] = float(parts[1].strip().replace('%',''))
            for key, starts in [('pos',['positive','positif']),
                                 ('neg',['negative','negatif']),
                                 ('neu',['neutral','netral'])]:
                if any(line.startswith(s) for s in starts):
                    p = line.split()
                    if len(p) >= 5:
                        m[f'precision_{key}'] = float(p[1])
                        m[f'recall_{key}']    = float(p[2])
                        m[f'f1_{key}']        = float(p[3])
                        m[f'support_{key}']   = int(p[4])
            if line.startswith('macro avg'):
                p = line.split()
                if len(p) >= 5: m['macro_f1'] = float(p[4])
            if line.startswith('weighted avg'):
                p = line.split()
                if len(p) >= 5: m['weighted_f1'] = float(p[4])
    except Exception:
        pass
    return m


@hasil_riset_bp.route('/hasil-riset')
@login_required
def index():
    # ── Total & label ─────────────────────────────────────────────────────────
    total_data = DataItem.query.join(Dataset)\
        .filter(Dataset.user_id == current_user.id).count()

    label_rows = db.session.query(
        DataItem.label, func.count(DataItem.id)
    ).join(Dataset).filter(Dataset.user_id == current_user.id)\
     .group_by(DataItem.label).all()
    db_counts = {(r[0] or 'unknown'): r[1] for r in label_rows}

    positif = db_counts.get('positif', 0)
    negatif = db_counts.get('negatif', 0)
    netral  = db_counts.get('netral',  0)
    pct_positif = round(positif / total_data * 100, 1) if total_data > 0 else 0
    pct_negatif = round(negatif / total_data * 100, 1) if total_data > 0 else 0
    pct_netral  = round(netral  / total_data * 100, 1) if total_data > 0 else 0

    # ── Preprocessing stats ───────────────────────────────────────────────────
    total_preprocessed = DataItem.query.join(Dataset)\
        .filter(Dataset.user_id == current_user.id,
                DataItem.is_preprocessed == True).count()
    belum_preprocessed = total_data - total_preprocessed

    # Ambil semua teks terpreprocessing untuk statistik
    prep_items = DataItem.query.join(Dataset)\
        .filter(Dataset.user_id == current_user.id,
                DataItem.is_preprocessed == True,
                DataItem.teks_preprocessed != None)\
        .with_entities(DataItem.teks_preprocessed, DataItem.teks).all()

    # Statistik teks
    panjang_prep   = [len(i.teks_preprocessed.split()) for i in prep_items if i.teks_preprocessed]
    panjang_asli   = [len(i.teks.split()) for i in prep_items if i.teks]
    rata_prep      = round(sum(panjang_prep) / len(panjang_prep), 1) if panjang_prep else 0
    rata_asli      = round(sum(panjang_asli) / len(panjang_asli), 1) if panjang_asli else 0
    maks_prep      = max(panjang_prep) if panjang_prep else 0
    min_prep       = min(panjang_prep) if panjang_prep else 0

    # Teks terpanjang & terpendek
    item_terpanjang = max(prep_items, key=lambda x: len(x.teks_preprocessed.split()) if x.teks_preprocessed else 0) if prep_items else None
    item_terpendek  = min(prep_items, key=lambda x: len(x.teks_preprocessed.split()) if x.teks_preprocessed else 999) if prep_items else None

    # Kata paling sering muncul (dari teks terpreprocessing)
    all_words = []
    for item in prep_items:
        if item.teks_preprocessed:
            all_words.extend(item.teks_preprocessed.split())
    top_kata = Counter(all_words).most_common(10)

    # ── Top kata per sentimen ─────────────────────────────────────────────────
    def get_top_words_by_label(label, n=10):
        items = DataItem.query.join(Dataset)\
            .filter(Dataset.user_id == current_user.id,
                    DataItem.label == label,
                    DataItem.is_preprocessed == True,
                    DataItem.teks_preprocessed != None).all()
        words = []
        for item in items:
            words.extend(item.teks_preprocessed.split())
        return Counter(words).most_common(n)

    top_positif = get_top_words_by_label('positif')
    top_negatif = get_top_words_by_label('negatif')
    top_netral  = get_top_words_by_label('netral')

    # ── Dataset info ──────────────────────────────────────────────────────────
    datasets = Dataset.query.filter_by(user_id=current_user.id)\
                            .order_by(Dataset.created_at.desc()).all()
    total_datasets = len(datasets)

    # ── Tabel sample ──────────────────────────────────────────────────────────
    sample_items = DataItem.query.join(Dataset)\
        .filter(Dataset.user_id == current_user.id,
                DataItem.is_preprocessed == True)\
        .all()
    tabel = [{
        'teks'             : item.teks[:120],
        'teks_preprocessed': (item.teks_preprocessed or '')[:120],
        'label'            : item.label,
        'dataset'          : item.dataset.nama,
    } for item in sample_items]

    # ── Chart per dataset ─────────────────────────────────────────────────────
    dataset_chart = db.session.query(
        Dataset.nama,
        func.sum(func.IF(DataItem.label == 'positif', 1, 0)).label('positif'),
        func.sum(func.IF(DataItem.label == 'negatif', 1, 0)).label('negatif'),
        func.sum(func.IF(DataItem.label == 'netral',  1, 0)).label('netral'),
    ).join(DataItem).filter(Dataset.user_id == current_user.id)\
     .group_by(Dataset.id, Dataset.nama)\
     .order_by(Dataset.created_at.asc()).all()

    # ── Evaluasi model dari classification_report.txt ─────────────────────────
    report_path = os.path.join(current_app.root_path, 'hasil_svm', 'classification_report.txt')
    report_text = ''
    if os.path.exists(report_path):
        with open(report_path, 'r', encoding='utf-8') as f:
            report_text = f.read()
    metrics = _parse_metrics(report_text)

    # ── Riwayat hasil klasifikasi SVM ─────────────────────────────────────────
    riwayat_klasifikasi = HasilKlasifikasi.query\
        .filter_by(user_id=current_user.id)\
        .order_by(HasilKlasifikasi.created_at.desc()).all()

    # Ambil yang terbaru untuk ditampilkan di stat cards
    last_klasifikasi = riwayat_klasifikasi[0] if riwayat_klasifikasi else None

    stats = {
        # Label
        'total_data'        : total_data,
        'positif'           : positif,
        'negatif'           : negatif,
        'netral'            : netral,
        'pct_positif'       : pct_positif,
        'pct_negatif'       : pct_negatif,
        'pct_netral'        : pct_netral,
        # Preprocessing
        'total_preprocessed': total_preprocessed,
        'belum_preprocessed': belum_preprocessed,
        'rata_prep'         : rata_prep,
        'rata_asli'         : rata_asli,
        'maks_prep'         : maks_prep,
        'min_prep'          : min_prep,
        'teks_terpanjang'   : item_terpanjang.teks[:300] if item_terpanjang else '-',
        'teks_terpendek'    : item_terpendek.teks[:300]  if item_terpendek  else '-',
        'top_kata'          : top_kata,
        # Top kata per sentimen
        'top_positif'       : top_positif,
        'top_negatif'       : top_negatif,
        'top_netral'        : top_netral,
        # Chart top kata per sentimen
        'chart_pos_labels'  : json.dumps([k[0] for k in top_positif]),
        'chart_pos_values'  : json.dumps([k[1] for k in top_positif]),
        'chart_neg_labels'  : json.dumps([k[0] for k in top_negatif]),
        'chart_neg_values'  : json.dumps([k[1] for k in top_negatif]),
        'chart_neu_labels'  : json.dumps([k[0] for k in top_netral]),
        'chart_neu_values'  : json.dumps([k[1] for k in top_netral]),
        # Dataset
        'total_datasets'    : total_datasets,
        'datasets'          : datasets,
        'tabel'             : tabel,
        # Evaluasi
        'akurasi'           : metrics['akurasi'],
        'precision_pos'     : metrics['precision_pos'],
        'recall_pos'        : metrics['recall_pos'],
        'f1_pos'            : metrics['f1_pos'],
        'support_pos'       : metrics['support_pos'],
        'precision_neg'     : metrics['precision_neg'],
        'recall_neg'        : metrics['recall_neg'],
        'f1_neg'            : metrics['f1_neg'],
        'support_neg'       : metrics['support_neg'],
        'precision_neu'     : metrics['precision_neu'],
        'recall_neu'        : metrics['recall_neu'],
        'f1_neu'            : metrics['f1_neu'],
        'support_neu'       : metrics['support_neu'],
        'macro_f1'          : metrics['macro_f1'],
        'weighted_f1'       : metrics['weighted_f1'],
        'has_report'        : bool(report_text),
        # Hasil Klasifikasi SVM
        'riwayat_klasifikasi': riwayat_klasifikasi,
        'last_klasifikasi'   : last_klasifikasi,
        'total_diklasifikasi': sum(r.total_data for r in riwayat_klasifikasi),
        'chart_svm_labels'   : json.dumps(['Positif', 'Negatif', 'Netral']),
        'chart_svm_values'   : json.dumps([
            sum(r.pred_positif for r in riwayat_klasifikasi),
            sum(r.pred_negatif for r in riwayat_klasifikasi),
            sum(r.pred_netral  for r in riwayat_klasifikasi),
        ]),
        # Charts
        'chart_pie_labels'  : json.dumps(['Positif','Negatif','Netral']),
        'chart_pie_values'  : json.dumps([positif, negatif, netral]),
        'chart_ds_labels'   : json.dumps([d.nama[:15] for d in dataset_chart]),
        'chart_ds_positif'  : json.dumps([int(d.positif or 0) for d in dataset_chart]),
        'chart_ds_negatif'  : json.dumps([int(d.negatif or 0) for d in dataset_chart]),
        'chart_ds_netral'   : json.dumps([int(d.netral  or 0) for d in dataset_chart]),
        'chart_kata_labels' : json.dumps([k[0] for k in top_kata]),
        'chart_kata_values' : json.dumps([k[1] for k in top_kata]),
    }

    return render_template('hasil_riset.html', stats=stats)