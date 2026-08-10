from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

STATUSES = ['Склад ЧелГУ', 'НашЭтаж', 'Хобби-Студия', 'На руках']
STATUS_TAKEN = 'На руках'


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    bookings = db.relationship('Booking', back_populates='user', lazy=True)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def display_name(self):
        return self.full_name or self.username


class Item(db.Model):
    __tablename__ = 'items'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), nullable=False, default='Склад ЧелГУ')
    holder = db.Column(db.String(100))
    holder_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    qr_filename = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    holder_user = db.relationship('User', foreign_keys=[holder_user_id])

    @property
    def is_taken(self):
        return self.status == STATUS_TAKEN

    def taken_by(self, user):
        return bool(user and user.is_authenticated and self.holder_user_id == user.id)


class ItemHistory(db.Model):
    __tablename__ = 'item_history'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    changed_at = db.Column(db.DateTime, default=utc_now)

    item = db.relationship('Item', backref=db.backref('history', lazy=True))
    user = db.relationship('User', foreign_keys=[user_id])


class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    prev_status = db.Column(db.String(50))
    taken_at = db.Column(db.DateTime, default=utc_now)
    returned_at = db.Column(db.DateTime, nullable=True)

    item = db.relationship('Item', backref=db.backref('bookings', lazy=True))
    user = db.relationship('User', back_populates='bookings')

    @property
    def is_active(self):
        return self.returned_at is None
