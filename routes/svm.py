from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Dataset, DataItem
import pandas as pd
import numpy as np
import os
import json
import joblib

svm_bp = Blueprint('svm', __name__)

# ── Path helper ───────────────────────────────────────────────────────────────
def model_dir():
    # ✅ Folder baru: WEB_DASHBOARD/model/
    return os.path.join(current_app.root_path, 'model')

# ── Cache model & vectorizer ──────────────────────────────────────────────────
_model      = None
_vectorizer = None

def get_model():
    global _model
    if _model is None:
        path = os.path.join(model_dir(), 'model_svm_smote.pkl')
        if os.path.exists(path):
            _model = joblib.load(path)
    return _model

def get_vectorizer():
    global _vectorizer
    if _vectorizer is None:
        path = os.path.join(model_dir(), 'tfidf_vectorizer.pkl')
        if os.path.exists(path):
            _vectorizer = joblib.load(path)
    return _vectorizer


# ── Halaman utama ─────────────────────────────────────────────────────────────
@svm_bp.route('/klasifikasi-svm')
@login_required
def index():
    model_ready      = os.path.exists(os.path.join(model_dir(), 'model_svm_smote.pkl'))
    vectorizer_ready = os.path.exists(os.path.join(model_dir(), 'tfidf_vectorizer.pkl'))

    datasets = Dataset.query.filter_by(user_id=current_user.id)\
                            .order_by(Dataset.created_at.desc()).all()
    total_db_preprocessed = DataItem.query\
        .join(Dataset)\
        .filter(Dataset.user_id == current_user.id,
                DataItem.is_preprocessed == True).count()

    stats = {
        'akurasi'              : 84.41,
        'datasets'             : datasets,
        'total_db_preprocessed': total_db_preprocessed,
        'model_ready'          : model_ready,
        'vectorizer_ready'     : vectorizer_ready,
        # kosongkan chart lama — tidak dipakai lagi
        'chart_label_data'     : json.dumps([0, 0, 0]),
        'chart_prediksi_data'  : json.dumps([0, 0, 0]),
    }

    return render_template('svm.html', stats=stats)


# ── Tabel hasil prediksi (dipanggil svm.html saat load) ──────────────────────
@svm_bp.route('/klasifikasi-svm/tabel-data', methods=['POST'])
@login_required
def tabel_data():
    # Endpoint ini dipertahankan agar url_for('svm.tabel_data') di svm.html tidak error.
    # Model baru tidak pakai file CSV statis — kembalikan response kosong yang aman.
    return jsonify({
        'success'    : True,
        'rows'       : [],
        'total'      : 0,
        'page'       : 1,
        'total_pages': 1,
    })


# ── Klasifikasi data dari DB (upload web) ────────────────────────────────────
@svm_bp.route('/klasifikasi-svm/klasifikasi-db', methods=['POST'])
@login_required
def klasifikasi_db():
    dataset_id = request.json.get('dataset_id')
    if not dataset_id:
        return jsonify({'success': False, 'message': 'Pilih dataset terlebih dahulu.'})

    model      = get_model()
    vectorizer = get_vectorizer()

    if not model:
        return jsonify({'success': False,
                        'message': 'Model tidak ditemukan. Pastikan model_svm_smote.pkl ada di folder model/'})
    if not vectorizer:
        return jsonify({'success': False,
                        'message': 'Vectorizer tidak ditemukan. Pastikan tfidf_vectorizer.pkl ada di folder model/'})

    items = DataItem.query.filter_by(
        dataset_id=dataset_id,
        is_preprocessed=True
    ).all()

    if not items:
        return jsonify({'success': False,
                        'message': 'Belum ada data yang dipreprocessing di dataset ini.'})

    # Prediksi — model baru pakai label Indonesia (positif/negatif/netral)
    teks_list = [item.teks_preprocessed for item in items]
    X         = vectorizer.transform(teks_list)   # sparse matrix, tidak perlu toarray()
    y_pred    = model.predict(X)

    # Susun hasil
    hasil = []
    for i, item in enumerate(items):
        pred       = str(y_pred[i])                          # positif / negatif / netral
        label_asli = (item.label or '').lower().strip()
        benar      = label_asli == pred.lower() if label_asli else None

        hasil.append({
            'id'        : item.id,
            'teks'      : item.teks[:200],
            'label_asli': item.label,
            'prediksi'  : pred,
            'confidence': None,   # LinearSVC tidak punya predict_proba
            'benar'     : benar,
        })

    pred_counts  = {}
    for h in hasil:
        pred_counts[h['prediksi']] = pred_counts.get(h['prediksi'], 0) + 1

    benar_count = sum(1 for h in hasil if h['benar'] is True)
    akurasi     = round(benar_count / len(hasil) * 100, 2) if hasil else 0

    return jsonify({
        'success'    : True,
        'total'      : len(hasil),
        'akurasi'    : akurasi,
        'benar'      : benar_count,
        'salah'      : len(hasil) - benar_count,
        'pred_counts': pred_counts,
        'hasil'      : hasil[:500],   # kirim max 500 baris ke frontend
        'message'    : f'Berhasil mengklasifikasi {len(hasil)} data.',
    })


# ── Prediksi teks baru (single input) ────────────────────────────────────────
@svm_bp.route('/klasifikasi-svm/prediksi-teks', methods=['POST'])
@login_required
def prediksi_teks():
    teks = request.json.get('teks', '').strip()
    if not teks:
        return jsonify({'success': False, 'message': 'Teks kosong.'})

    model      = get_model()
    vectorizer = get_vectorizer()

    if not model:
        return jsonify({'success': False, 'message': 'Model tidak ditemukan di folder model/.'})
    if not vectorizer:
        return jsonify({'success': False, 'message': 'Vectorizer tidak ditemukan di folder model/.'})

    from utils.preprocessor import preprocess
    hasil_prep  = preprocess(teks)
    teks_bersih = hasil_prep['result']

    X    = vectorizer.transform([teks_bersih])
    pred = str(model.predict(X)[0])   # positif / negatif / netral

    return jsonify({
        'success'          : True,
        'prediksi'         : pred,
        'probabilitas'     : {},       # LinearSVC tidak punya probabilitas
        'teks_asli'        : teks,
        'teks_preprocessed': teks_bersih,
    })


# ── Download hasil klasifikasi ────────────────────────────────────────────────
@svm_bp.route('/klasifikasi-svm/download-hasil', methods=['POST'])
@login_required
def download_hasil():
    import io
    from flask import send_file

    dataset_id = request.json.get('dataset_id')
    fmt        = request.json.get('format', 'csv')

    if not dataset_id:
        return jsonify({'success': False, 'message': 'Dataset tidak dipilih.'})

    model      = get_model()
    vectorizer = get_vectorizer()
    if not model or not vectorizer:
        return jsonify({'success': False, 'message': 'Model atau vectorizer tidak ditemukan.'})

    items = DataItem.query.filter_by(dataset_id=dataset_id, is_preprocessed=True).all()
    if not items:
        return jsonify({'success': False, 'message': 'Belum ada data yang dipreprocessing.'})

    teks_list = [item.teks_preprocessed for item in items]
    X         = vectorizer.transform(teks_list)
    y_pred    = model.predict(X)

    rows = []
    for i, item in enumerate(items):
        pred       = str(y_pred[i])
        label_asli = (item.label or '').lower().strip()
        benar      = label_asli == pred.lower() if label_asli else None
        rows.append({
            'teks_asli'        : item.teks,
            'teks_preprocessed': item.teks_preprocessed,
            'label_asli'       : item.label,
            'label_prediksi'   : pred,
            'benar'            : benar,
        })

    df = pd.DataFrame(rows)

    if fmt == 'excel':
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Hasil Klasifikasi')
        buf.seek(0)
        return send_file(buf,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name='hasil_klasifikasi.xlsx')
    else:
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        buf.seek(0)
        return send_file(io.BytesIO(buf.getvalue().encode('utf-8-sig')),
                         mimetype='text/csv', as_attachment=True,
                         download_name='hasil_klasifikasi.csv')