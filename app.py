import os
from flask import Flask
from flask_login import LoginManager
from config import Config
from models import db, User
from routes import main

login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message = 'Войдите в аккаунт чтобы бронировать вещи'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def _migrate():
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)

    # Добавляем недостающие колонки если их нет
    new_columns = {
        'items': [
            ('holder_id', 'INTEGER'),
            ('photo',     'VARCHAR(200)'),
        ],
        'item_history': [
            ('note',    'VARCHAR(300)'),
            ('user_id', 'INTEGER'),
        ],
    }

    for table, columns in new_columns.items():
        if not inspector.has_table(table):
            continue
        existing = {c['name'] for c in inspector.get_columns(table)}
        for col_name, col_type in columns:
            if col_name not in existing:
                db.session.execute(text(
                    f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}'
                ))
    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()
        _migrate()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
