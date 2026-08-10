from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

STATUSES = ['Склад ЧелГУ', 'НашЭтаж', 'Хобби-Студия', 'На руках']

def utc_now():
    return datetime.now(timezone.utc)

class Item(db.Model):
    __tablename__ = 'items'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status      = db.Column(db.String(50), nullable=False, default='Склад ЧелГУ')
    holder      = db.Column(db.String(100))
    photo       = db.Column(db.String(200))   # имя файла фото предмета
    created_at  = db.Column(db.DateTime, default=utc_now)
    updated_at  = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    def __repr__(self):
        return f'<Item {self.name}>'

class ItemHistory(db.Model):
    __tablename__ = 'item_history'

    id         = db.Column(db.Integer, primary_key=True)
    item_id    = db.Column(db.Integer, db.ForeignKey('items.id'), nullable=False)
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50), nullable=False)
    note       = db.Column(db.String(300))
    changed_at = db.Column(db.DateTime, default=utc_now)

    item = db.relationship('Item', backref=db.backref('history', lazy=True))
