from app import create_app
from models import db, Item, User
from utils import generate_qr

app = create_app()

with app.app_context():
    if Item.query.count() == 0:
        items = [
            Item(name='Проектор Epson', description='Проектор для презентаций и мероприятий', status='Склад ЧелГУ'),
            Item(name='Ноутбук ASUS', description='Ноутбук для работы на мероприятиях', status='НашЭтаж'),
            Item(name='Микрофон беспроводной', description='Микрофон для выступлений', status='Хобби-Студия'),
            Item(name='Колонка JBL', description='Портативная колонка', status='Хобби-Студия'),
            Item(name='Настольная игра Манчкин', description='Игра для клубных вечеров', status='НашЭтаж'),
            Item(name='Штатив для камеры', description='Алюминиевый штатив 1.6 м', status='Склад ЧелГУ'),
        ]
        db.session.add_all(items)
        db.session.commit()

        for item in Item.query.all():
            item.qr_filename = generate_qr(item.id)
        db.session.commit()
        print('Тестовые предметы добавлены')
    else:
        print('Предметы уже есть, пропускаю')

    print('Пользователей в базе:', User.query.count())
