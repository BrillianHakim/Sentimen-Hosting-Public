from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Dataset, DataItem, HasilKlasifikasi
import pandas as pd
import numpy as np
import os
import json
import joblib

svm_bp = Blueprint('svm', __name__)

# ── Path helper ───────────────────────────────────────────────────────────────
def hasil_dir():
    return os.path.join(current_app.root_path, 'model')

def tfidf_dir():
    return os.path.join(current_app.root_path, 'model')

# ── Cache model & vectorizer ──────────────────────────────────────────────────
_model     = None
_vectorizer = None

def get_model():
    global _model
    if _model is None:
        path = os.path.join(hasil_dir(), 'model_svm_smote.pkl')
        if os.path.exists(path):
            _model = joblib.load(path)
    return _model

def get_vectorizer():
    global _vectorizer
    if _vectorizer is None:
        path = os.path.join(tfidf_dir(), 'tfidf_vectorizer.pkl')
        if os.path.exists(path):
            _vectorizer = joblib.load(path)
    return _vectorizer


# ── Halaman utama ─────────────────────────────────────────────────────────────
@svm_bp.route('/klasifikasi-svm')
@login_required
def index():
    # ── Baca classification report ────────────────────────────────────────────
    report_path = os.path.join(hasil_dir(), 'classification_report.txt')
    report_text = ''
    if os.path.exists(report_path):
        with open(report_path, 'r', encoding='utf-8') as f:
            report_text = f.read()

    metrics = _parse_metrics(report_text)

    # ── Baca hasil prediksi CSV ───────────────────────────────────────────────
    csv_path = os.path.join(hasil_dir(), 'hasil_prediksi.csv')
    total = benar = salah = 0
    label_counts    = {'positive': 0, 'negative': 0, 'neutral': 0}
    prediksi_counts = {'positive': 0, 'negative': 0, 'neutral': 0}

    if os.path.exists(csv_path):
        df    = pd.read_csv(csv_path)
        total = len(df)
        benar = int(df['benar'].sum()) if 'benar' in df.columns else 0
        salah = total - benar

        if 'label_corrected' in df.columns:
            for lbl, cnt in df['label_corrected'].value_counts().items():
                label_counts[str(lbl).lower()] = int(cnt)
        if 'label_prediksi' in df.columns:
            for lbl, cnt in df['label_prediksi'].value_counts().items():
                prediksi_counts[str(lbl).lower()] = int(cnt)

    # ── Data dari DB (upload web) ─────────────────────────────────────────────
    datasets = Dataset.query.filter_by(user_id=current_user.id)\
                            .order_by(Dataset.created_at.desc()).all()
    total_db_preprocessed = DataItem.query\
        .join(Dataset)\
        .filter(Dataset.user_id == current_user.id,
                DataItem.is_preprocessed == True).count()

    # ── Status model & vectorizer ─────────────────────────────────────────────
    model_ready      = os.path.exists(os.path.join(hasil_dir(), 'svm_model.pkl'))
    vectorizer_ready = os.path.exists(os.path.join(tfidf_dir(), 'tfidf_vectorizer.pkl'))

    stats = {
        'total'               : total,
        'benar'               : benar,
        'salah'               : salah,
        'akurasi'             : metrics.get('akurasi', 0),
        'precision_pos'       : metrics.get('precision_pos', 0),
        'recall_pos'          : metrics.get('recall_pos', 0),
        'f1_pos'              : metrics.get('f1_pos', 0),
        'precision_neg'       : metrics.get('precision_neg', 0),
        'recall_neg'          : metrics.get('recall_neg', 0),
        'f1_neg'              : metrics.get('f1_neg', 0),
        'precision_neu'       : metrics.get('precision_neu', 0),
        'recall_neu'          : metrics.get('recall_neu', 0),
        'f1_neu'              : metrics.get('f1_neu', 0),
        'label_counts'        : label_counts,
        'prediksi_counts'     : prediksi_counts,
        'report_text'         : report_text,
        'chart_label_data'    : json.dumps([label_counts['positive'],    label_counts['negative'],    label_counts['neutral']]),
        'chart_prediksi_data' : json.dumps([prediksi_counts['positive'], prediksi_counts['negative'], prediksi_counts['neutral']]),
        # DB
        'datasets'            : datasets,
        'total_db_preprocessed': total_db_preprocessed,
        # Status
        'model_ready'         : model_ready,
        'vectorizer_ready'    : vectorizer_ready,
    }

    return render_template('svm.html', stats=stats)


# ── Tabel hasil prediksi (file CSV) ──────────────────────────────────────────
@svm_bp.route('/klasifikasi-svm/tabel-data', methods=['POST'])
@login_required
def tabel_data():
    csv_path = os.path.join(hasil_dir(), 'hasil_prediksi.csv')
    if not os.path.exists(csv_path):
        return jsonify({'success': False, 'message': 'File hasil prediksi tidak ditemukan.'})

    df           = pd.read_csv(csv_path)
    page         = request.json.get('page', 1)
    per_page     = 50
    filter_label = request.json.get('filter_label', 'all')
    filter_benar = request.json.get('filter_benar', 'all')

    if filter_label != 'all' and 'label_prediksi' in df.columns:
        df = df[df['label_prediksi'] == filter_label]
    if filter_benar == 'benar' and 'benar' in df.columns:
        df = df[df['benar'] == True]
    elif filter_benar == 'salah' and 'benar' in df.columns:
        df = df[df['benar'] == False]

    total_filtered = len(df)
    start  = (page - 1) * per_page
    cols   = ['original_text', 'label_corrected', 'label_prediksi', 'benar', 'sumber']
    cols   = [c for c in cols if c in df.columns]
    rows   = df[cols].iloc[start:start+per_page].fillna('').to_dict(orient='records')

    return jsonify({
        'success'    : True,
        'rows'       : rows,
        'total'      : total_filtered,
        'page'       : page,
        'total_pages': (total_filtered + per_page - 1) // per_page,
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
        return jsonify({'success': False, 'message': 'Model SVM tidak ditemukan di folder model.'})
    if not vectorizer:
        return jsonify({'success': False, 'message': 'TF-IDF vectorizer tidak ditemukan di folder hasil_tfidf/.'})

    # Ambil data yang sudah dipreprocessing
    items = DataItem.query.filter_by(
        dataset_id=dataset_id,
        is_preprocessed=True
    ).all()

    if not items:
        return jsonify({'success': False, 'message': 'Belum ada data yang dipreprocessing di dataset ini.'})

    # Mapping label Indonesia → Inggris untuk dibandingkan dengan prediksi model
    # (model masih pakai label Inggris sampai training ulang selesai)
    label_map = {
    'positif' : 'positif',
    'negatif' : 'negatif',
    'netral'  : 'netral',
}

    # Prediksi
    teks_list  = [item.teks_preprocessed for item in items]
    X          = vectorizer.transform(teks_list)
    X_dense    = X.toarray()
    y_pred     = model.predict(X_dense)
    y_proba    = model.predict_proba(X_dense) if hasattr(model, 'predict_proba') else None
    classes    = model.classes_.tolist()

    # Susun hasil
    hasil = []
    for i, item in enumerate(items):
        pred       = str(y_pred[i])
        conf       = float(np.max(y_proba[i])) * 100 if y_proba is not None else None
        label_norm = label_map.get(item.label.lower(), item.label.lower()) if item.label else None
        benar      = label_norm == pred.lower() if label_norm else None
        hasil.append({
            'id'         : item.id,
            'teks'       : item.teks[:200],
            'label_asli' : item.label,
            'prediksi'   : pred,
            'confidence' : round(conf, 1) if conf else None,
            'benar'      : benar,
        })

    # Hitung statistik
    pred_counts = {}
    for h in hasil:
        pred_counts[h['prediksi']] = pred_counts.get(h['prediksi'], 0) + 1

    benar_count = sum(1 for h in hasil if h['benar'] == True)
    akurasi     = round(benar_count / len(hasil) * 100, 2) if hasil else 0

    # Simpan hasil ke DB
    try:
        riwayat = HasilKlasifikasi(
            user_id     = current_user.id,
            dataset_id  = int(dataset_id),
            total_data  = len(hasil),
            benar       = benar_count,
            salah       = len(hasil) - benar_count,
            akurasi     = akurasi,
            pred_positif= pred_counts.get('positif', 0),
            pred_negatif= pred_counts.get('negatif', 0),
            pred_netral = pred_counts.get('netral',  0),
        )
        db.session.add(riwayat)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({
        'success'    : True,
        'total'      : len(hasil),
        'akurasi'    : akurasi,
        'benar'      : benar_count,
        'salah'      : len(hasil) - benar_count,
        'pred_counts': pred_counts,
        'hasil'      : hasil,
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

    if not model or not vectorizer:
        return jsonify({'success': False, 'message': 'Model atau vectorizer tidak ditemukan.'})

    from utils.preprocessor import preprocess
    hasil_prep  = preprocess(teks)
    teks_bersih = hasil_prep['result']

    X       = vectorizer.transform([teks_bersih])
    X_dense = X.toarray()
    pred    = str(model.predict(X_dense)[0])
    proba   = model.predict_proba(X_dense)[0] if hasattr(model, 'predict_proba') else None
    classes = model.classes_.tolist()

    prob_dict = {}
    if proba is not None:
        prob_dict = {c: round(float(p) * 100, 1) for c, p in zip(classes, proba)}

    return jsonify({
        'success'           : True,
        'prediksi'          : pred,
        'probabilitas'      : prob_dict,
        'teks_asli'         : teks,
        'teks_preprocessed' : teks_bersih,
    })


# ── Download hasil klasifikasi ────────────────────────────────────────────────
@svm_bp.route('/klasifikasi-svm/download-hasil', methods=['POST'])
@login_required
def download_hasil():
    """Download hasil klasifikasi DB sebagai CSV atau Excel."""
    import io
    from flask import send_file

    dataset_id = request.json.get('dataset_id')
    fmt        = request.json.get('format', 'csv')  # 'csv' atau 'excel'

    if not dataset_id:
        return jsonify({'success': False, 'message': 'Dataset tidak dipilih.'})

    model      = get_model()
    vectorizer = get_vectorizer()
    if not model or not vectorizer:
        return jsonify({'success': False, 'message': 'Model atau vectorizer tidak ditemukan.'})

    items = DataItem.query.filter_by(dataset_id=dataset_id, is_preprocessed=True).all()
    if not items:
        return jsonify({'success': False, 'message': 'Belum ada data yang dipreprocessing.'})

    label_map = {
        'positif':'positive','negatif':'negative','netral':'neutral',
        'positive':'positive','negative':'negative','neutral':'neutral',
    }

    teks_list = [item.teks_preprocessed for item in items]
    X_dense   = vectorizer.transform(teks_list).toarray()
    y_pred    = model.predict(X_dense)
    y_proba   = model.predict_proba(X_dense) if hasattr(model, 'predict_proba') else None

    rows = []
    for i, item in enumerate(items):
        pred       = str(y_pred[i])
        conf       = round(float(np.max(y_proba[i])) * 100, 2) if y_proba is not None else None
        label_norm = label_map.get((item.label or '').lower(), item.label)
        benar      = label_norm == pred.lower() if label_norm else None
        rows.append({
            'teks_asli'        : item.teks,
            'teks_preprocessed': item.teks_preprocessed,
            'label_asli'       : item.label,
            'label_prediksi'   : pred,
            'confidence_%'     : conf,
            'benar'            : benar,
        })

    df = pd.DataFrame(rows)

    if fmt == 'excel':
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Hasil Klasifikasi')
        buf.seek(0)
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name='hasil_klasifikasi.xlsx')
    else:
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        buf.seek(0)
        return send_file(io.BytesIO(buf.getvalue().encode('utf-8-sig')),
                         mimetype='text/csv', as_attachment=True,
                         download_name='hasil_klasifikasi.csv')

@login_required
def prediksi_teks():
    teks = request.json.get('teks', '').strip()
    if not teks:
        return jsonify({'success': False, 'message': 'Teks kosong.'})

    model      = get_model()
    vectorizer = get_vectorizer()

    if not model or not vectorizer:
        return jsonify({'success': False, 'message': 'Model atau vectorizer tidak ditemukan.'})

    # Preprocessing dulu
    from utils.preprocessor import preprocess
    hasil_prep = preprocess(teks)
    teks_bersih = hasil_prep['result']

    X       = vectorizer.transform([teks_bersih])
    X_dense = X.toarray()  # convert sparse → dense
    pred    = str(model.predict(X_dense)[0])
    proba   = model.predict_proba(X_dense)[0] if hasattr(model, 'predict_proba') else None
    classes = model.classes_.tolist()

    prob_dict = {}
    if proba is not None:
        prob_dict = {c: round(float(p) * 100, 1) for c, p in zip(classes, proba)}

    return jsonify({
        'success'        : True,
        'prediksi'       : pred,
        'probabilitas'   : prob_dict,
        'teks_asli'      : teks,
        'teks_preprocessed': teks_bersih,
    })


# ── Helper parse metrics ──────────────────────────────────────────────────────
def _parse_metrics(text):
    m = {'akurasi': 0,
         'precision_pos': 0, 'recall_pos': 0, 'f1_pos': 0,
         'precision_neg': 0, 'recall_neg': 0, 'f1_neg': 0,
         'precision_neu': 0, 'recall_neu': 0, 'f1_neu': 0}
    if not text:
        return m
    try:
        for line in text.splitlines():
            line = line.strip()
            if 'Akurasi' in line or 'akurasi' in line:
                parts = line.split(':')
                if len(parts) > 1:
                    m['akurasi'] = float(parts[1].strip().replace('%', ''))
            if line.startswith('positive') or line.startswith('positif'):
                p = line.split()
                if len(p) >= 4:
                    m['precision_pos'] = float(p[1])
                    m['recall_pos']    = float(p[2])
                    m['f1_pos']        = float(p[3])
            if line.startswith('negative') or line.startswith('negatif'):
                p = line.split()
                if len(p) >= 4:
                    m['precision_neg'] = float(p[1])
                    m['recall_neg']    = float(p[2])
                    m['f1_neg']        = float(p[3])
            if line.startswith('neutral') or line.startswith('netral'):
                p = line.split()
                if len(p) >= 4:
                    m['precision_neu'] = float(p[1])
                    m['recall_neu']    = float(p[2])
                    m['f1_neu']        = float(p[3])
    except Exception:
        pass
    return m