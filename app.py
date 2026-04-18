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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(preprocessing_bp)

    # Root redirect
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))

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
                role  = 'Peneliti Akademik',
            )
            admin.set_password('Bintang12#')
            db.session.add(admin)
            db.session.commit()
            print('✅  Akun dibuat → email: bintangbrillianhakim@gmail.com | password: Bintang12#')


if __name__ == '__main__':
    env = os.environ.get('FLASK_ENV', 'development')
    application = create_app(env)
    application.run(debug=True)