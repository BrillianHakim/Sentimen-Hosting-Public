from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_bcrypt import Bcrypt
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()


# ─────────────────────────────────────────
#  User
# ─────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    password   = db.Column(db.String(255), nullable=False)
    role       = db.Column(db.String(50), default='Peneliti Akademik')
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    datasets   = db.relationship('Dataset', backref='owner', lazy=True,
                                 cascade='all, delete-orphan')

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

    def get_initials(self):
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.name[:2].upper()


# ─────────────────────────────────────────
#  Dataset  (metadata file upload)
# ─────────────────────────────────────────
class Dataset(db.Model):
    __tablename__ = 'datasets'

    id         = db.Column(db.Integer, primary_key=True)
    nama       = db.Column(db.String(200), nullable=False)
    filename   = db.Column(db.String(255))
    total_rows = db.Column(db.Integer, default=0)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items      = db.relationship('DataItem', backref='dataset', lazy=True,
                                 cascade='all, delete-orphan')

    @property
    def positif_count(self):
        return DataItem.query.filter_by(dataset_id=self.id, label='positif').count()

    @property
    def negatif_count(self):
        return DataItem.query.filter_by(dataset_id=self.id, label='negatif').count()

    @property
    def netral_count(self):
        return DataItem.query.filter_by(dataset_id=self.id, label='netral').count()


# ─────────────────────────────────────────
#  DataItem  (setiap baris dataset)
# ─────────────────────────────────────────
class DataItem(db.Model):
    __tablename__ = 'data_items'

    id                = db.Column(db.Integer, primary_key=True)
    dataset_id        = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=False)
    teks              = db.Column(db.Text, nullable=False)
    teks_preprocessed = db.Column(db.Text)
    label             = db.Column(db.String(50))
    is_preprocessed   = db.Column(db.Boolean, default=False)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────
#  UserAnalisisFile (riwayat analisis file user)
# ─────────────────────────────────────────
class UserAnalisisFile(db.Model):
    __tablename__ = 'user_analisis_file'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    nama_file    = db.Column(db.String(255))
    total_data   = db.Column(db.Integer, default=0)
    positif      = db.Column(db.Integer, default=0)
    negatif      = db.Column(db.Integer, default=0)
    netral       = db.Column(db.Integer, default=0)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    user         = db.relationship('User', backref=db.backref('analisis_files', lazy=True))


# ─────────────────────────────────────────
#  UserPrediksiTeks (riwayat prediksi teks user)
# ─────────────────────────────────────────
class UserPrediksiTeks(db.Model):
    __tablename__ = 'user_prediksi_teks'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    teks         = db.Column(db.Text, nullable=False)
    prediksi     = db.Column(db.String(50))
    confidence   = db.Column(db.Float)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    user         = db.relationship('User', backref=db.backref('prediksi_teks', lazy=True))


# ─────────────────────────────────────────
#  UserAnalisisDetail (detail baris hasil analisis file user)
# ─────────────────────────────────────────
class UserAnalisisDetail(db.Model):
    __tablename__ = 'user_analisis_detail'

    id           = db.Column(db.Integer, primary_key=True)
    analisis_id  = db.Column(db.Integer, db.ForeignKey('user_analisis_file.id'), nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    teks         = db.Column(db.Text, nullable=False)
    prediksi     = db.Column(db.String(50))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    analisis     = db.relationship('UserAnalisisFile', backref=db.backref('details', lazy=True, cascade='all, delete-orphan'))


# ─────────────────────────────────────────
#  HasilKlasifikasi (hasil klasifikasi SVM admin)
# ─────────────────────────────────────────
class HasilKlasifikasi(db.Model):
    __tablename__ = 'hasil_klasifikasi'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    dataset_id   = db.Column(db.Integer, db.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False)
    total_data   = db.Column(db.Integer, default=0)
    benar        = db.Column(db.Integer, default=0)
    salah        = db.Column(db.Integer, default=0)
    akurasi      = db.Column(db.Float,   default=0)
    pred_positif = db.Column(db.Integer, default=0)
    pred_negatif = db.Column(db.Integer, default=0)
    pred_netral  = db.Column(db.Integer, default=0)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    user         = db.relationship('User',    backref=db.backref('hasil_klasifikasi', lazy=True, cascade='all, delete-orphan'))
    dataset      = db.relationship('Dataset', backref=db.backref('hasil_klasifikasi', lazy=True, cascade='all, delete-orphan'))