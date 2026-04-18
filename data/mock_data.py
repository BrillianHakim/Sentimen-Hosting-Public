from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# ─── User Model ───────────────────────────────────────────
class User(UserMixin):
    def __init__(self, id, name, email, password, role='Peneliti Akademik'):
        self.id       = id
        self.name     = name
        self.email    = email
        self.password = generate_password_hash(password)
        self.role     = role

    def check_password(self, password):
        return check_password_hash(self.password, password)


# ─── Data User (dummy) ────────────────────────────────────
USERS = {
    '1': User('1', 'Admin User', 'admin@skripsi.ac.id', 'admin123')
}

# Mapping email → user untuk login
USERS_BY_EMAIL = {u.email: u for u in USERS.values()}


# ─── Data Sentimen (dummy) ────────────────────────────────
DASHBOARD_DATA = {
    'total_data'    : 1240,
    'positif'       : 850,
    'negatif'       : 390,
    'akurasi'       : 92.5,
    'precision'     : 0.91,
    'recall'        : 0.89,
    'f1_score'      : 0.90,
    'pct_positif'   : 68.5,
    'pct_negatif'   : 31.5,
}

AKTIVITAS = [
    {'icon': 'check',   'color': 'green',  'text': 'Pengujian Model Selesai',      'waktu': '2 JAM LALU'},
    {'icon': 'refresh', 'color': 'blue',   'text': 'Dataset Diperbarui (N=1,240)', 'waktu': '4 JAM LALU'},
    {'icon': 'edit',    'color': 'yellow', 'text': 'Penyesuaian Stopwords',        'waktu': '1 HARI LALU'},
]