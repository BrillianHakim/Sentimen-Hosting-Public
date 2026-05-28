from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
from flask import abort
from models import db, Dataset, DataItem, UserAnalisisFile, UserPrediksiTeks, UserAnalisisDetail
from sqlalchemy import func
import json, os, joblib, numpy as np, pandas as pd

user_bp = Blueprint('user', __name__)

# ── Decorator: hanya role User ────────────────────────────────────────────────
def user_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.role not in ['User', 'Mahasiswa']:
            abort(403)
        return f(*args, **kwargs)
    return decorated

def hasil_dir():
    return os.path.join(current_app.root_path, 'model')

def tfidf_dir():
    return os.path.join(current_app.root_path, 'model')

_model = None
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

def _parse_akurasi(text):
    if not text:
        return 0
    for line in text.splitlines():
        line = line.strip()
        # Format: Accuracy : 0.8556 (85.56%)
        if 'Accuracy' in line or 'accuracy' in line:
            # Cari angka dalam kurung (85.56%)
            import re
            match = re.search(r'\((\d+\.?\d*)%\)', line)
            if match:
                return float(match.group(1))
            # Fallback: ambil angka desimal lalu kali 100
            match = re.search(r':\s*(0\.\d+)', line)
            if match:
                return round(float(match.group(1)) * 100, 2)
        # Format lama: Akurasi : 84.28%
        if 'Akurasi' in line:
            parts = line.split(':')
            if len(parts) > 1:
                try:
                    return float(parts[1].strip().replace('%', ''))
                except:
                    pass
    return 0


# ── Beranda User ──────────────────────────────────────────────────────────────
@user_bp.route('/user/beranda')
@login_required
@user_required
def beranda():
    # Statistik dari DB admin
    total_data = DataItem.query.join(Dataset).count()
    label_rows = db.session.query(
        DataItem.label, func.count(DataItem.id)
    ).join(Dataset).group_by(DataItem.label).all()
    db_counts = {(r[0] or ''): r[1] for r in label_rows}

    positif = db_counts.get('positif', 0)
    negatif = db_counts.get('negatif', 0)
    netral  = db_counts.get('netral', 0)
    pct_positif = round(positif / total_data * 100, 1) if total_data > 0 else 0
    pct_negatif = round(negatif / total_data * 100, 1) if total_data > 0 else 0
    pct_netral  = round(netral  / total_data * 100, 1) if total_data > 0 else 0

    report_path = os.path.join(hasil_dir(), 'classification_report.txt')
    report_text = open(report_path, 'r', encoding='utf-8').read() if os.path.exists(report_path) else ''
    akurasi = _parse_akurasi(report_text)

    stats = {
        'total_data' : total_data,
        'positif'    : positif,
        'negatif'    : negatif,
        'netral'     : netral,
        'pct_positif': pct_positif,
        'pct_negatif': pct_negatif,
        'pct_netral' : pct_netral,
        'akurasi'    : akurasi,
        'chart_labels': json.dumps(['Positif', 'Negatif', 'Netral']),
        'chart_values': json.dumps([positif, negatif, netral]),
    }
    return render_template('user/beranda.html', stats=stats)


# ── Analisis File ─────────────────────────────────────────────────────────────
@user_bp.route('/user/analisis-file')
@login_required
@user_required
def analisis_file():
    return render_template('user/analisis_file.html')


@user_bp.route('/user/analisis-file/proses', methods=['POST'])
@login_required
@user_required
def proses_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'File tidak ditemukan.'})

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'message': 'Pilih file terlebih dahulu.'})

    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in ['csv', 'xlsx', 'xls']:
        return jsonify({'success': False, 'message': 'Format tidak didukung. Gunakan CSV atau Excel.'})

    try:
        df = pd.read_csv(file, encoding='utf-8', on_bad_lines='skip') if ext == 'csv' else pd.read_excel(file)
        df.columns = [c.strip().lower() for c in df.columns]

        text_col = next((c for c in ['teks','text','tweet','komentar','content','ulasan','review'] if c in df.columns), None)

        if not text_col:
            return jsonify({'success': False, 'message': f'Kolom teks tidak ditemukan. Kolom tersedia: {", ".join(df.columns)}'})

        model      = get_model()
        vectorizer = get_vectorizer()
        if not model or not vectorizer:
            return jsonify({'success': False, 'message': 'Model SVM belum tersedia.'})

        from utils.preprocessor import preprocess

        hasil = []
        label_counts = {'positif': 0, 'negatif': 0, 'netral': 0}

        for _, row in df.iterrows():
            teks  = str(row[text_col]).strip()
            if not teks or teks == 'nan':
                continue
            prep        = preprocess(teks)
            teks_bersih = prep['result']

            X    = vectorizer.transform([teks_bersih]).toarray()
            pred = str(model.predict(X)[0])
            proba= model.predict_proba(X)[0] if hasattr(model, 'predict_proba') else None
            conf = round(float(np.max(proba)) * 100, 1) if proba is not None else None

            label_counts[pred] = label_counts.get(pred, 0) + 1
            hasil.append({
                'teks'    : teks[:150],
                'prediksi': pred,
                'confidence': conf,
            })

        total = len(hasil)

        # Simpan riwayat ke DB
        riwayat = UserAnalisisFile(
            user_id   = current_user.id,
            nama_file = file.filename,
            total_data= total,
            positif   = label_counts.get('positif', 0),
            negatif   = label_counts.get('negatif', 0),
            netral    = label_counts.get('netral',  0),
        )
        db.session.add(riwayat)
        db.session.flush()  # dapatkan id riwayat

        # Simpan detail per baris
        for row in hasil:
            detail = UserAnalisisDetail(
                analisis_id = riwayat.id,
                user_id     = current_user.id,
                teks        = row['teks'],
                prediksi    = row['prediksi'],
            )
            db.session.add(detail)
        db.session.commit()

        return jsonify({
            'success'     : True,
            'total'       : total,
            'hasil'       : hasil,
            'label_counts': label_counts,
            'chart_labels': json.dumps(['Positif', 'Negatif', 'Netral']),
            'chart_values': json.dumps([label_counts.get('positif',0), label_counts.get('negatif',0), label_counts.get('netral',0)]),
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Gagal memproses: {str(e)}'})


# ── Prediksi Teks ─────────────────────────────────────────────────────────────
@user_bp.route('/user/prediksi-teks')
@login_required
@user_required
def prediksi_teks():
    return render_template('user/prediksi_teks.html')


@user_bp.route('/user/prediksi-teks/proses', methods=['POST'])
@login_required
@user_required
def proses_prediksi():
    teks = request.json.get('teks', '').strip()
    if not teks:
        return jsonify({'success': False, 'message': 'Teks tidak boleh kosong.'})

    model      = get_model()
    vectorizer = get_vectorizer()
    if not model or not vectorizer:
        return jsonify({'success': False, 'message': 'Model belum tersedia.'})

    from utils.preprocessor import preprocess
    prep        = preprocess(teks)
    teks_bersih = prep['result']

    X      = vectorizer.transform([teks_bersih]).toarray()
    pred   = str(model.predict(X)[0])
    proba  = model.predict_proba(X)[0] if hasattr(model, 'predict_proba') else None
    classes= model.classes_.tolist()
    prob_dict = {str(c): round(float(p)*100, 1) for c, p in zip(classes, proba)} if proba is not None else {}
    conf      = prob_dict.get(pred, None)

    # Simpan riwayat ke DB
    riwayat = UserPrediksiTeks(
        user_id   = current_user.id,
        teks      = teks[:500],
        prediksi  = pred,
        confidence= conf,
    )
    db.session.add(riwayat)
    db.session.commit()

    return jsonify({
        'success'     : True,
        'prediksi'    : pred,
        'probabilitas': prob_dict,
        'teks_prep'   : teks_bersih,
    })



# ── Hapus riwayat analisis file ───────────────────────────────────────────────
@user_bp.route('/user/hapus-analisis/<int:id>', methods=['POST'])
@login_required
@user_required
def hapus_analisis(id):
    item = UserAnalisisFile.query.filter_by(id=id, user_id=current_user.id).first()
    if not item:
        return jsonify({'success': False, 'message': 'Data tidak ditemukan.'})
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Riwayat berhasil dihapus.'})


@user_bp.route('/user/hapus-analisis-semua', methods=['POST'])
@login_required
@user_required
def hapus_analisis_semua():
    UserAnalisisFile.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Semua riwayat analisis berhasil dihapus.'})


# ── Hapus riwayat prediksi teks ───────────────────────────────────────────────
@user_bp.route('/user/hapus-prediksi/<int:id>', methods=['POST'])
@login_required
@user_required
def hapus_prediksi(id):
    item = UserPrediksiTeks.query.filter_by(id=id, user_id=current_user.id).first()
    if not item:
        return jsonify({'success': False, 'message': 'Data tidak ditemukan.'})
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Riwayat berhasil dihapus.'})


@user_bp.route('/user/hapus-prediksi-semua', methods=['POST'])
@login_required
@user_required
def hapus_prediksi_semua():
    UserPrediksiTeks.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Semua riwayat prediksi berhasil dihapus.'})
@user_bp.route('/user/hasil-riset')
@login_required
@user_required
def hasil_riset():
    report_path = os.path.join(hasil_dir(), 'classification_report.txt')
    report_text = open(report_path, 'r', encoding='utf-8').read() if os.path.exists(report_path) else ''
    akurasi = _parse_akurasi(report_text)

    total_data = DataItem.query.count()

    label_rows = db.session.query(
        DataItem.label, func.count(DataItem.id)
    ).group_by(DataItem.label).all()
    db_counts  = {(r[0] or ''): r[1] for r in label_rows}

    positif = db_counts.get('positif', 0)
    negatif = db_counts.get('negatif', 0)
    netral  = db_counts.get('netral',  0)

    # Riwayat analisis file user ini
    riwayat_file = UserAnalisisFile.query\
        .filter_by(user_id=current_user.id)\
        .order_by(UserAnalisisFile.created_at.desc()).all()

    # Riwayat prediksi teks user ini
    riwayat_teks = UserPrediksiTeks.query\
        .filter_by(user_id=current_user.id)\
        .order_by(UserPrediksiTeks.created_at.desc()).all()

    # ── Chart dari riwayat file user ─────────────────────────────────────────
    total_positif_user = sum(r.positif for r in riwayat_file)
    total_negatif_user = sum(r.negatif for r in riwayat_file)
    total_netral_user  = sum(r.netral  for r in riwayat_file)
    total_user         = total_positif_user + total_negatif_user + total_netral_user
    total_analisis  = len(riwayat_file)
    total_prediksi  = len(riwayat_teks)
    total_file_data = sum(r.total_data for r in riwayat_file)

    # ── Top kata dari hasil analisis file user ────────────────────────────────
    from collections import Counter as WordCounter

    def top_words_from_analisis(label, n=10):
        items = UserAnalisisDetail.query.filter_by(
            user_id=current_user.id, prediksi=label
        ).all()
        words = []
        for item in items:
            if item.teks:
                words.extend([w for w in item.teks.lower().split() if len(w) > 3])
        return WordCounter(words).most_common(n)

    top_positif        = top_words_from_analisis('positif')
    top_negatif        = top_words_from_analisis('negatif')
    top_netral         = top_words_from_analisis('netral')
    total_pred_positif = UserAnalisisDetail.query.filter_by(user_id=current_user.id, prediksi='positif').count()
    total_pred_negatif = UserAnalisisDetail.query.filter_by(user_id=current_user.id, prediksi='negatif').count()
    total_pred_netral  = UserAnalisisDetail.query.filter_by(user_id=current_user.id, prediksi='netral').count()

    stats = {
        'akurasi'           : akurasi,
        'total_data'        : total_data,
        'positif'           : positif,
        'negatif'           : negatif,
        'netral'            : netral,
        'total_analisis'    : total_analisis,
        'total_prediksi'    : total_prediksi,
        'total_file_data'   : total_file_data,
        'riwayat_file'      : riwayat_file,
        'riwayat_teks'      : riwayat_teks,
        'top_positif'       : top_positif,
        'top_negatif'       : top_negatif,
        'top_netral'        : top_netral,
        'total_pred_positif': total_pred_positif,
        'total_pred_negatif': total_pred_negatif,
        'total_pred_netral' : total_pred_netral,
        'chart_labels'      : json.dumps(['Positif', 'Negatif', 'Netral']),
        'chart_values'      : json.dumps([total_positif_user, total_negatif_user, total_netral_user]),
        'total_user'        : total_user,
    }
    return render_template('user/hasil_riset.html', stats=stats)