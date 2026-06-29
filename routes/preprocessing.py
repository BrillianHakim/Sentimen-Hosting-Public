from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Dataset, DataItem
from utils.preprocessor import preprocess
import pandas as pd
import io

preprocessing_bp = Blueprint('preprocessing', __name__)


@preprocessing_bp.route('/preprocessing')
@login_required
def index():
    datasets = Dataset.query.filter_by(user_id=current_user.id)\
                            .order_by(Dataset.created_at.desc()).all()
    return render_template('preprocessing.html', datasets=datasets)


@preprocessing_bp.route('/preprocessing/sample', methods=['POST'])
@login_required
def sample():
    """Preview preprocessing untuk satu teks (uji coba langsung)."""
    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'message': 'Teks kosong.'})
    result = preprocess(text)
    return jsonify({
        'success' : True,
        'steps'   : {
            'original'    : result['original'],
            'case_folding': result['case_folding'],
            'cleaning'    : result['cleaning'],
            'slang_norm'  : result['slang_norm'],
            'tokenisasi'  : result['tokenisasi'],
            'stopword'    : result['stopword'],
            'stemming'    : result['stemming'],
            'result'      : result['result'],
        }
    })


@preprocessing_bp.route('/preprocessing/run', methods=['POST'])
@login_required
def run():
    """Proses dataset per batch 50 data."""
    dataset_id = request.json.get('dataset_id')
    offset     = request.json.get('offset', 0)  # mulai dari data ke berapa
    batch_size = 50

    if not dataset_id:
        return jsonify({'success': False, 'message': 'Dataset tidak dipilih.'})

    dataset = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id).first()
    if not dataset:
        return jsonify({'success': False, 'message': 'Dataset tidak ditemukan.'})

    # Ambil hanya yang belum diproses, batch 50
    items = DataItem.query.filter_by(
        dataset_id=dataset_id,
        is_preprocessed=False
    ).limit(batch_size).all()

    if not items:
        # Semua sudah selesai
        total = DataItem.query.filter_by(dataset_id=dataset_id).count()
        return jsonify({
            'success'  : True,
            'done'     : True,
            'processed': total,
            'message'  : f'Semua {total} data selesai dipreproses!',
        })

    processed = 0
    for item in items:
        result = preprocess(item.teks)
        item.teks_preprocessed = result['result']
        item.is_preprocessed   = True
        processed += 1

    db.session.commit()

    total      = DataItem.query.filter_by(dataset_id=dataset_id).count()
    done_count = DataItem.query.filter_by(dataset_id=dataset_id, is_preprocessed=True).count()

    return jsonify({
        'success'   : True,
        'done'      : False,  # masih ada sisa
        'processed' : done_count,
        'total'     : total,
        'message'   : f'Diproses {done_count} dari {total} data...',
    })
    """Proses seluruh dataset, simpan hasil ke DB, stream progress via JSON."""
    dataset_id = request.json.get('dataset_id')
    if not dataset_id:
        return jsonify({'success': False, 'message': 'Dataset tidak dipilih.'})

    dataset = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id).first()
    if not dataset:
        return jsonify({'success': False, 'message': 'Dataset tidak ditemukan.'})

    items = DataItem.query.filter_by(dataset_id=dataset_id).all()
    if not items:
        return jsonify({'success': False, 'message': 'Dataset kosong.'})

    processed = 0
    for item in items:
        result = preprocess(item.teks)
        item.teks_preprocessed = result['result']
        item.is_preprocessed   = True
        processed += 1

    db.session.commit()

    return jsonify({
        'success'  : True,
        'processed': processed,
        'message'  : f'{processed} data berhasil dipreproses.',
    })


@preprocessing_bp.route('/preprocessing/preview-data', methods=['POST'])
@login_required
def preview_data():
    """Ambil 20 baris pertama dataset (sebelum & sesudah) untuk ditampilkan."""
    dataset_id = request.json.get('dataset_id')
    dataset = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id).first()
    if not dataset:
        return jsonify({'success': False, 'message': 'Dataset tidak ditemukan.'})

    items = DataItem.query.filter_by(dataset_id=dataset_id).all()
    rows  = [{
        'id'          : item.id,
        'teks'        : item.teks,
        'hasil'       : item.teks_preprocessed or '-',
        'label'       : item.label,
        'preprocessed': item.is_preprocessed,
    } for item in items]

    total      = DataItem.query.filter_by(dataset_id=dataset_id).count()
    done_count = DataItem.query.filter_by(dataset_id=dataset_id, is_preprocessed=True).count()

    return jsonify({
        'success'   : True,
        'rows'      : rows,
        'total'     : total,
        'done_count': done_count,
    })


@preprocessing_bp.route('/preprocessing/download', methods=['POST'])
@login_required
def download():
    """Download hasil preprocessing sebagai CSV atau Excel."""
    dataset_id = request.json.get('dataset_id')
    fmt        = request.json.get('format', 'csv')

    if not dataset_id:
        return jsonify({'success': False, 'message': 'Dataset tidak dipilih.'})

    dataset = Dataset.query.filter_by(id=dataset_id, user_id=current_user.id).first()
    if not dataset:
        return jsonify({'success': False, 'message': 'Dataset tidak ditemukan.'})

    items = DataItem.query.filter_by(dataset_id=dataset_id).all()
    if not items:
        return jsonify({'success': False, 'message': 'Dataset kosong.'})

    rows = [{
        'teks_asli'        : item.teks,
        'teks_preprocessed': item.teks_preprocessed or '',
        'label'            : item.label,
        'status'           : 'Sudah' if item.is_preprocessed else 'Belum',
    } for item in items]

    df        = pd.DataFrame(rows)
    nama_file = dataset.nama.replace(' ', '_')

    if fmt == 'excel':
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Preprocessing')
        buf.seek(0)
        return send_file(buf,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=f'preprocessing_{nama_file}.xlsx')
    else:
        buf = io.BytesIO(df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'))
        buf.seek(0)
        return send_file(buf, mimetype='text/csv',
                         as_attachment=True,
                         download_name=f'preprocessing_{nama_file}.csv')