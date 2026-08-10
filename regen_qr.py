 from app import create_app
from models import db, Item
from utils import generate_qr

app = create_app()

with app.app_context():
    for item in Item.query.all():
        item.qr_filename = generate_qr(item.id)
    db.session.commit()
    print("✅ QR-коды перегенерированы в правильную папку!")