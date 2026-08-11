from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

STATUSES = ['Склад ЧелГУ', 'НашЭтаж', 'Хобби-Студия', 'На руках']

def utc_now():
    return datetime.now(timezone.utc)

class User(db.Model):
    __tablename__ = 'users'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    password   = db.Column(db.String(256), nullable=False)
    is_admin   = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    def set_password(self, raw):
        self.password = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password, raw)

    # flask-login требует эти свойства
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f'<User {self.email}>'

class Item(db.Model):
    __tablename__ = 'items'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status      = db.Column(db.String(50), nullable=False, default='Склад ЧелГУ')
    holder      = db.Column(db.String(100))
    holder_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    photo       = db.Column(db.String(200))        # legacy: имя файла на диске
    photo_data  = db.Column(db.LargeBinary)        # сама картинка в БД
    photo_mime  = db.Column(db.String(50))         # image/jpeg, image/png ...
    created_at  = db.Column(db.DateTime, default=utc_now)
    updated_at  = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    holder_user = db.relationship('User', foreign_keys=[holder_id])

    @property
    def has_photo(self):
        return self.photo_data is not None

    def __repr__(self):
        return f'<Item {self.name}>'

class ItemHistory(db.Model):
    __tablename__ = 'item_history'

    id         = db.Column(db.Integer, primary_key=True)
    item_id    = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50), nullable=False)
    note       = db.Column(db.String(300))
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    changed_at = db.Column(db.DateTime, default=utc_now)

    item = db.relationship('Item', backref=db.backref('history', lazy=True))
    user = db.relationship('User', foreign_keys=[user_id])
