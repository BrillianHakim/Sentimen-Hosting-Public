from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, User

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile')
@login_required
def index():
    return render_template('profile.html')


@profile_bp.route('/profile/edit', methods=['POST'])
@login_required
def edit():
    name  = request.form.get('name', '').strip()
    role  = request.form.get('role', '').strip()
    email = request.form.get('email', '').strip().lower()

    if not all([name, role, email]):
        flash('Semua field wajib diisi.', 'danger')
        return redirect(url_for('profile.index'))

    # Cek email sudah dipakai user lain
    existing = User.query.filter(User.email == email, User.id != current_user.id).first()
    if existing:
        flash('Email sudah digunakan akun lain.', 'danger')
        return redirect(url_for('profile.index'))

    current_user.name  = name
    current_user.role  = role
    current_user.email = email
    db.session.commit()

    flash('Profil berhasil diperbarui!', 'success')
    return redirect(url_for('profile.index'))


@profile_bp.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    old_pw   = request.form.get('old_password', '')
    new_pw   = request.form.get('new_password', '')
    confirm  = request.form.get('confirm_password', '')

    if not all([old_pw, new_pw, confirm]):
        flash('Semua field password wajib diisi.', 'danger')
        return redirect(url_for('profile.index'))

    if not current_user.check_password(old_pw):
        flash('Password lama tidak sesuai.', 'danger')
        return redirect(url_for('profile.index'))

    if len(new_pw) < 8:
        flash('Password baru minimal 8 karakter.', 'danger')
        return redirect(url_for('profile.index'))

    if new_pw != confirm:
        flash('Konfirmasi password tidak cocok.', 'danger')
        return redirect(url_for('profile.index'))

    current_user.set_password(new_pw)
    db.session.commit()

    flash('Password berhasil diubah!', 'success')
    return redirect(url_for('profile.index'))