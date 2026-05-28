from flask import Flask, redirect, url_for
from flask_login import LoginManager
from config import config
from models import db, bcrypt, User
import os

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)

    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Silakan login terlebih dahulu.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.upload import upload_bp
    from routes.preprocessing import preprocessing_bp
    from routes.profile import profile_bp
    from routes.svm import svm_bp
    from routes.hasil_riset import hasil_riset_bp
    from routes.update_data import update_data_bp
    from routes.user_dashboard import user_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(preprocessing_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(svm_bp)
    app.register_blueprint(hasil_riset_bp)
    app.register_blueprint(update_data_bp)
    app.register_blueprint(user_bp)

    # Root → langsung ke login
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))


    # Create tables on first run
    with app.app_context():
        db.create_all()
        _seed_admin(app)

    return app


def _seed_admin(app):
    """Buat akun admin default jika belum ada user."""
    with app.app_context():
        if User.query.count() == 0:
            admin = User(
                name  = 'Bintang Brillian Hakim',
                email = 'bintangbrillianhakim@gmail.com',
                role  = 'Peneliti',
            )
            admin.set_password('Bintang12#')
            db.session.add(admin)
            db.session.commit()
            print('✅  Akun dibuat → email: bintangbrillianhakim@gmail.com | password: Bintang12#')


if __name__ == '__main__':
    env = os.environ.get('FLASK_ENV', 'development')
    application = create_app(env)
    application.run(debug=True)