from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Dataset, DataItem, HasilKlasifikasi
import pandas as pd
import os
from werkzeug.utils import secure_filename

upload_bp = Blueprint('upload', __name__)

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@upload_bp.route('/upload', methods=['GET'])
@login_required
def index():
    # Riwayat upload milik user ini
    datasets = Dataset.query.filter_by(user_id=current_user.id)\
                            .order_by(Dataset.created_at.desc()).all()
    return render_template('upload.html', datasets=datasets)


@upload_bp.route('/upload/preview', methods=['POST'])
@login_required
def preview():
    """Baca file, validasi kolom, kembalikan preview JSON."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Tidak ada file yang dikirim.'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Pilih file terlebih dahulu.'})

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Format file tidak didukung. Gunakan CSV atau Excel.'})

    try:
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext == 'csv':
            df = pd.read_csv(file, encoding='utf-8', on_bad_lines='skip')
        else:
            df = pd.read_excel(file)

        # Normalisasi nama kolom (lowercase + strip)
        df.columns = [c.strip().lower() for c in df.columns]

        # Deteksi kolom teks & label
        text_candidates  = ['teks', 'text', 'tweet', 'komentar', 'content', 'ulasan', 'review', 'konten']
        label_candidates = ['label', 'sentimen', 'sentiment', 'kategori', 'class', 'kelas']

        text_col  = next((c for c in text_candidates  if c in df.columns), None)
        label_col = next((c for c in label_candidates if c in df.columns), None)

        errors = []
        if not text_col:
            errors.append(f'Kolom teks tidak ditemukan. Kolom tersedia: {", ".join(df.columns)}')
        if not label_col:
            errors.append(f'Kolom label tidak ditemukan. Kolom tersedia: {", ".join(df.columns)}')

        if errors:
            return jsonify({'success': False, 'message': ' | '.join(errors)})

        # Statistik label
        label_counts = df[label_col].value_counts().to_dict()
        label_counts = {str(k): int(v) for k, v in label_counts.items()}

        # Preview semua baris
        preview_data = df[[text_col, label_col]].fillna('').to_dict(orient='records')

        return jsonify({
            'success'     : True,
            'total_rows'  : len(df),
            'columns'     : list(df.columns),
            'text_col'    : text_col,
            'label_col'   : label_col,
            'label_counts': label_counts,
            'preview'     : preview_data,
            'filename'    : secure_filename(file.filename),
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Gagal membaca file: {str(e)}'})


@upload_bp.route('/upload/save', methods=['POST'])
@login_required
def save():
    """Simpan dataset ke database."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'File tidak ditemukan.'})

    file      = request.files['file']
    nama      = request.form.get('nama_dataset', file.filename).strip()
    text_col  = request.form.get('text_col', '').strip()
    label_col = request.form.get('label_col', '').strip()

    try:
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext == 'csv':
            df = pd.read_csv(file, encoding='utf-8', on_bad_lines='skip')
        else:
            df = pd.read_excel(file)

        df.columns = [c.strip().lower() for c in df.columns]
        df = df[[text_col, label_col]].dropna()

        # Simpan metadata dataset
        dataset = Dataset(
            nama        = nama,
            filename    = secure_filename(file.filename),
            total_rows  = len(df),
            user_id     = current_user.id,
        )
        db.session.add(dataset)
        db.session.flush()  # dapatkan dataset.id

        # Simpan setiap baris sebagai DataItem
        items = [
            DataItem(
                dataset_id = dataset.id,
                teks       = str(row[text_col])[:2000],
                label      = str(row[label_col]).strip().lower(),
            )
            for _, row in df.iterrows()
        ]
        db.session.bulk_save_objects(items)
        db.session.commit()

        return jsonify({
            'success'   : True,
            'message'   : f'Dataset "{nama}" berhasil disimpan ({len(df)} baris).',
            'dataset_id': dataset.id,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Gagal menyimpan: {str(e)}'})


@upload_bp.route('/upload/delete/<int:dataset_id>', methods=['POST'])
@login_required
def delete(dataset_id):
    """Hapus dataset pakai bulk delete (cepat, tidak timeout di database remote)."""
    dataset = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id).first_or_404()
    nama = dataset.nama

    DataItem.query.filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
    HasilKlasifikasi.query.filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
    db.session.delete(dataset)
    db.session.commit()

    flash(f'Dataset "{nama}" berhasil dihapus.', 'info')
    return redirect(url_for('upload.index'))


@upload_bp.route('/upload/delete-all', methods=['POST'])
@login_required
def delete_all():
    """Hapus semua dataset milik user pakai bulk delete (cepat, tidak timeout)."""
    datasets = Dataset.query.filter_by(user_id=current_user.id).all()
    jumlah   = len(datasets)

    if jumlah == 0:
        flash('Tidak ada dataset yang dihapus.', 'warning')
        return redirect(url_for('upload.index'))

    dataset_ids = [ds.id for ds in datasets]

    DataItem.query.filter(DataItem.dataset_id.in_(dataset_ids)).delete(synchronize_session=False)
    HasilKlasifikasi.query.filter(HasilKlasifikasi.dataset_id.in_(dataset_ids)).delete(synchronize_session=False)
    Dataset.query.filter(Dataset.id.in_(dataset_ids)).delete(synchronize_session=False)

    db.session.commit()
    flash(f'{jumlah} dataset beserta seluruh datanya berhasil dihapus.', 'success')
    return redirect(url_for('upload.index'))