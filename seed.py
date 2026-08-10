from app import create_app
from models import db, Item

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()

    items = [
        Item(name='Проектор Epson',         description='Проектор для презентаций и мероприятий', status='Склад ЧелГУ'),
        Item(name='Ноутбук ASUS',            description='Ноутбук для работы на мероприятиях',    status='НашЭтаж'),
        Item(name='Микрофон беспроводной',   description='Микрофон для выступлений',               status='На руках', holder='Иванов И.И.'),
        Item(name='Колонка JBL',             description='Портативная колонка',                    status='Хобби-Студия'),
        Item(name='Настольная игра Манчкин', description='Игра для клубных вечеров',               status='НашЭтаж'),
    ]

    db.session.add_all(items)
    db.session.commit()

    print('✅ Тестовые данные добавлены!')
