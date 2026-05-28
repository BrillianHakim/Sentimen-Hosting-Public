from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Dataset, DataItem
from werkzeug.utils import secure_filename
import pandas as pd

update_data_bp = Blueprint('update_data', __name__)

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Halaman utama ─────────────────────────────────────────────────────────────
@update_data_bp.route('/update-data')
@login_required
def index():
    datasets = Dataset.query.filter_by(user_id=current_user.id)\
                            .order_by(Dataset.created_at.desc()).all()
    return render_template('update_data.html', datasets=datasets)


# ── Preview file sebelum digabung ─────────────────────────────────────────────
@update_data_bp.route('/update-data/preview', methods=['POST'])
@login_required
def preview():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Tidak ada file.'})

    file = request.files['file']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Format file tidak didukung. Gunakan CSV atau Excel.'})

    try:
        ext = file.filename.rsplit('.', 1)[1].lower()
        df  = pd.read_csv(file, encoding='utf-8', on_bad_lines='skip') if ext == 'csv' \
              else pd.read_excel(file)
        df.columns = [c.strip().lower() for c in df.columns]

        text_col  = next((c for c in ['teks','text','tweet','komentar','content','ulasan','review'] if c in df.columns), None)
        label_col = next((c for c in ['label','sentimen','sentiment','kategori','class','kelas']    if c in df.columns), None)

        errors = []
        if not text_col:  errors.append(f'Kolom teks tidak ditemukan. Kolom tersedia: {", ".join(df.columns)}')
        if not label_col: errors.append(f'Kolom label tidak ditemukan. Kolom tersedia: {", ".join(df.columns)}')
        if errors:
            return jsonify({'success': False, 'message': ' | '.join(errors)})

        label_counts = {str(k): int(v) for k, v in df[label_col].value_counts().to_dict().items()}
        preview_data = df[[text_col, label_col]].fillna('').to_dict(orient='records')

        return jsonify({
            'success'     : True,
            'total_rows'  : len(df),
            'text_col'    : text_col,
            'label_col'   : label_col,
            'label_counts': label_counts,
            'preview'     : preview_data,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Gagal membaca file: {str(e)}'})


# ── Gabungkan file ke dataset yang dipilih ────────────────────────────────────
@update_data_bp.route('/update-data/gabung', methods=['POST'])
@login_required
def gabung():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'File tidak ditemukan.'})

    file       = request.files['file']
    dataset_id = request.form.get('dataset_id')
    text_col   = request.form.get('text_col', '').strip()
    label_col  = request.form.get('label_col', '').strip()
    skip_duplikat = request.form.get('skip_duplikat') == 'true'

    dataset = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id).first()
    if not dataset:
        return jsonify({'success': False, 'message': 'Dataset tidak ditemukan.'})

    try:
        ext = file.filename.rsplit('.', 1)[1].lower()
        df  = pd.read_csv(file, encoding='utf-8', on_bad_lines='skip') if ext == 'csv' \
              else pd.read_excel(file)
        df.columns = [c.strip().lower() for c in df.columns]
        df = df[[text_col, label_col]].dropna()

        # Ambil teks yang sudah ada untuk cek duplikat
        existing_teks = set()
        if skip_duplikat:
            existing = DataItem.query.filter_by(dataset_id=dataset.id)\
                                     .with_entities(DataItem.teks).all()
            existing_teks = {e.teks.strip().lower() for e in existing}

        ditambah = 0
        dilewati = 0
        items    = []

        for _, row in df.iterrows():
            teks  = str(row[text_col]).strip()
            label = str(row[label_col]).strip().lower()
            if skip_duplikat and teks.lower() in existing_teks:
                dilewati += 1
                continue
            items.append(DataItem(
                dataset_id = dataset.id,
                teks       = teks[:2000],
                label      = label,
            ))
            ditambah += 1

        if items:
            db.session.bulk_save_objects(items)
            dataset.total_rows += ditambah
            db.session.commit()

        return jsonify({
            'success' : True,
            'ditambah': ditambah,
            'dilewati': dilewati,
            'message' : f'{ditambah} data berhasil ditambahkan ke "{dataset.nama}". {dilewati} data dilewati (duplikat).',
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Gagal menambahkan: {str(e)}'})


# ── Input manual satu data ────────────────────────────────────────────────────
@update_data_bp.route('/update-data/manual', methods=['POST'])
@login_required
def manual():
    dataset_id = request.json.get('dataset_id')
    teks       = request.json.get('teks', '').strip()
    label      = request.json.get('label', '').strip().lower()

    if not all([dataset_id, teks, label]):
        return jsonify({'success': False, 'message': 'Semua field wajib diisi.'})
    if label not in ['positif', 'negatif', 'netral']:
        return jsonify({'success': False, 'message': 'Label harus: positif, negatif, atau netral.'})

    dataset = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id).first()
    if not dataset:
        return jsonify({'success': False, 'message': 'Dataset tidak ditemukan.'})

    # Cek duplikat
    existing = DataItem.query.filter_by(dataset_id=dataset.id, teks=teks).first()
    if existing:
        return jsonify({'success': False, 'message': 'Teks ini sudah ada di dataset.'})

    item = DataItem(dataset_id=dataset.id, teks=teks[:2000], label=label)
    db.session.add(item)
    dataset.total_rows += 1
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Data berhasil ditambahkan ke "{dataset.nama}".',
        'item'   : {'id': item.id, 'teks': teks, 'label': label},
    })


# ── Hapus satu data item ──────────────────────────────────────────────────────
@update_data_bp.route('/update-data/hapus-item', methods=['POST'])
@login_required
def hapus_item():
    item_id = request.json.get('item_id')
    item    = DataItem.query.join(Dataset)\
                .filter(DataItem.id == item_id,
                        Dataset.user_id == current_user.id).first()
    if not item:
        return jsonify({'success': False, 'message': 'Data tidak ditemukan.'})

    dataset = item.dataset
    db.session.delete(item)
    if dataset.total_rows > 0:
        dataset.total_rows -= 1
    db.session.commit()
    return jsonify({'success': True, 'message': 'Data berhasil dihapus.'})