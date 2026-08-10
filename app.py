import os

from flask import Flask
from flask_login import LoginManager
from sqlalchemy import inspect, text

from config import Config
from models import db, User
from routes import main

login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message = 'Войдите в аккаунт, чтобы бронировать вещи'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def _auto_migrate():
    inspector = inspect(db.engine)

    wanted = {
        'users': {
            'full_name': 'VARCHAR(120)',
        },
        'items': {
            'holder_user_id': 'INTEGER',
        },
        'item_history': {
            'user_id': 'INTEGER',
        },
    }

    for table, columns in wanted.items():
        if not inspector.has_table(table):
            continue

        existing = {c['name'] for c in inspector.get_columns(table)}

        for column, ddl_type in columns.items():
            if column not in existing:
                db.session.execute(
                    text(
                        f'ALTER TABLE {table} '
                        f'ADD COLUMN {column} {ddl_type}'
                    )
                )

                # Для существующих пользователей заполняем новое поле.
                if table == 'users' and column == 'full_name':
                    db.session.execute(
                        text(
                            'UPDATE users '
                            'SET full_name = username '
                            'WHERE full_name IS NULL'
                        )
                    )

    db.session.commit()


def _ensure_admin():
    login = os.getenv('ADMIN_LOGIN', 'admin')
    password = os.getenv('ADMIN_PASSWORD', 'geekcult2026')
    user = User.query.filter_by(username=login).first()
    if user is None:
        user = User(username=login, full_name='Администратор', is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
    elif not user.is_admin:
        user.is_admin = True
        db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()
        _auto_migrate()
        _ensure_admin()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
