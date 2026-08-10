from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

STATUSES = ['Склад ЧелГУ', 'НашЭтаж', 'Хобби-Студия', 'На руках']

def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(100), unique=True, nullable=False)
    email         = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=utc_now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Item(db.Model):
    __tablename__ = 'items'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status      = db.Column(db.String(50), nullable=False, default='Склад ЧелГУ')
    holder      = db.Column(db.String(100))   # имя пользователя, кто взял
    holder_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    photo       = db.Column(db.String(200))
    created_at  = db.Column(db.DateTime, default=utc_now)
    updated_at  = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    holder_user = db.relationship('User', backref='borrowed_items')

    def __repr__(self):
        return f'<Item {self.name}>'


class ItemHistory(db.Model):
    __tablename__ = 'item_history'

    id         = db.Column(db.Integer, primary_key=True)
    item_id    = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50), nullable=False)
    note       = db.Column(db.String(300))
    changed_by = db.Column(db.String(100))   # username кто изменил
    changed_at = db.Column(db.DateTime, default=utc_now)

    item = db.relationship('Item', backref=db.backref('history', lazy=True))
