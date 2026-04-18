from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from models import db, Dataset, DataItem
from utils.preprocessor import preprocess

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

    items = DataItem.query.filter_by(dataset_id=dataset_id).limit(20).all()
    rows  = [{
        'id'        : item.id,
        'teks'      : item.teks,
        'hasil'     : item.teks_preprocessed or '-',
        'label'     : item.label,
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