from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

# Blokir akses /register
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    abort(404)

# ──────────────────────────────────────────────
#  LOGIN
# ──────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    error = None
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember_me') == 'on'

        if not email or not password:
            error = 'Email dan password wajib diisi.'
        else:
            user = User.query.filter_by(email=email).first()
            if user and user.check_password(password):
                if not user.is_active:
                    error = 'Akun Anda dinonaktifkan.'
                else:
                    login_user(user, remember=remember)
                    user.last_login = datetime.utcnow()
                    db.session.commit()
                    next_page = request.args.get('next')
                    flash(f'Selamat datang, {user.name}!', 'success')
                    return redirect(next_page or url_for('dashboard.index'))
            else:
                error = 'Email atau password salah.'

    return render_template('login.html', error=error)


# ──────────────────────────────────────────────
#  LUPA PASSWORD
# ──────────────────────────────────────────────
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    error   = None
    success = None

    if request.method == 'POST':
        email       = request.form.get('email', '').strip().lower()
        new_password = request.form.get('new_password', '')
        confirm     = request.form.get('confirm_password', '')

        if not all([email, new_password, confirm]):
            error = 'Semua field wajib diisi.'
        elif len(new_password) < 8:
            error = 'Password minimal 8 karakter.'
        elif new_password != confirm:
            error = 'Konfirmasi password tidak cocok.'
        else:
            user = User.query.filter_by(email=email).first()
            if not user:
                error = 'Email tidak ditemukan.'
            else:
                user.set_password(new_password)
                db.session.commit()
                success = 'Password berhasil diubah! Silakan login.'

    return render_template('forgot_password.html', error=error, success=success)


# ──────────────────────────────────────────────
#  LOGOUT
# ──────────────────────────────────────────────
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah keluar dari sistem.', 'info')
    return redirect(url_for('auth.login'))