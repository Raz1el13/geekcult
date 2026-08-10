import io
import os
import csv
import qrcode
import requests
from werkzeug.utils import secure_filename

from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, send_file, Response)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func

from models import db, Item, ItemHistory, User, STATUSES, utc_now

main = Blueprint('main', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'photos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── HTTP Basic Auth для /admin ─────────────────────────────────────────────────
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth     = request.authorization
        login    = os.getenv('ADMIN_LOGIN',    'admin')
        password = os.getenv('ADMIN_PASSWORD', 'geekcult2026')
        if not auth or not (auth.username == login and auth.password == password):
            return Response('Нужна авторизация', 401,
                            {'WWW-Authenticate': 'Basic realm="Admin"'})
        return f(*args, **kwargs)
    return decorated


def send_telegram(text: str):
    token   = os.getenv('TG_BOT_TOKEN')
    chat_id = os.getenv('TG_CHAT_ID')
    if not token or not chat_id:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=5,
        )
    except Exception:
        pass


# ── Регистрация ────────────────────────────────────────────────────────────────
@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')

        error = None
        if not username or not email or not password:
            error = 'Заполните все поля'
        elif password != confirm:
            error = 'Пароли не совпадают'
        elif len(password) < 6:
            error = 'Пароль должен быть не менее 6 символов'
        elif User.query.filter_by(username=username).first():
            error = 'Такой логин уже занят'
        elif User.query.filter_by(email=email).first():
            error = 'Этот e-mail уже зарегистрирован'

        if error:
            flash(error, 'danger')
            return render_template('register.html')

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash('Добро пожаловать! Вы успешно зарегистрировались.', 'success')
        return redirect(url_for('main.index'))

    return render_template('register.html')


# ── Вход ───────────────────────────────────────────────────────────────────────
@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('Неверный логин или пароль', 'danger')
            return render_template('login.html')

        login_user(user, remember=request.form.get('remember') == 'on')
        flash(f'Привет, {user.username}!', 'success')
        next_page = request.args.get('next')
        return redirect(next_page or url_for('main.index'))

    return render_template('login.html')


# ── Выход ──────────────────────────────────────────────────────────────────────
@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из аккаунта', 'info')
    return redirect(url_for('main.index'))


# ── Забронировать вещь ─────────────────────────────────────────────────────────
@main.route('/item/<int:item_id>/book', methods=['POST'])
@login_required
def book_item(item_id):
    item = db.get_or_404(Item, item_id)

    if item.status == 'На руках':
        flash('Эта вещь уже занята', 'warning')
        return redirect(url_for('main.item_detail', item_id=item_id))

    old_status = item.status

    db.session.add(ItemHistory(
        item_id    = item.id,
        old_status = old_status,
        new_status = 'На руках',
        note       = f'Забронировано пользователем {current_user.username}',
        changed_by = current_user.username,
    ))

    item.status    = 'На руках'
    item.holder    = current_user.username
    item.holder_id = current_user.id
    item.updated_at = utc_now()
    db.session.commit()

    send_telegram(
        f'📦 <b>{item.name}</b>\n{old_status} → <b>На руках</b>\n'
        f'👤 Забронировал: {current_user.username}'
    )
    flash(f'Вы забронировали «{item.name}»!', 'success')
    return redirect(url_for('main.item_detail', item_id=item_id))


# ── Вернуть вещь ───────────────────────────────────────────────────────────────
@main.route('/item/<int:item_id>/return', methods=['POST'])
@login_required
def return_item(item_id):
    item = db.get_or_404(Item, item_id)

    # Вернуть может только тот, кто взял
    if item.holder_id != current_user.id:
        flash('Вы не можете вернуть чужую вещь', 'danger')
        return redirect(url_for('main.item_detail', item_id=item_id))

    old_status = item.status
    new_status = 'Склад ЧелГУ'

    db.session.add(ItemHistory(
        item_id    = item.id,
        old_status = old_status,
        new_status = new_status,
        note       = f'Возвращено пользователем {current_user.username}',
        changed_by = current_user.username,
    ))

    item.status     = new_status
    item.holder     = None
    item.holder_id  = None
    item.updated_at = utc_now()
    db.session.commit()

    send_telegram(
        f'📦 <b>{item.name}</b>\n{old_status} → <b>{new_status}</b>\n'
        f'👤 Вернул: {current_user.username}'
    )
    flash(f'Вы вернули «{item.name}»', 'info')
    return redirect(url_for('main.item_detail', item_id=item_id))


# ── Главная ────────────────────────────────────────────────────────────────────
@main.route('/')
def index():
    status_filter = request.args.get('status')
    q = request.args.get('q', '').strip()

    query = Item.query
    if status_filter and status_filter in STATUSES:
        query = query.filter_by(status=status_filter)
    if q:
        query = query.filter(func.lower(Item.name).contains(func.lower(q)))

    items = query.order_by(Item.updated_at.desc()).all()
    return render_template('index.html', items=items, statuses=STATUSES)


@main.route('/item/<int:item_id>')
def item_detail(item_id):
    item = db.get_or_404(Item, item_id)
    return render_template('item.html', item=item)


@main.route('/stats')
def stats():
    status_counts = db.session.query(
        Item.status, func.count(Item.id)
    ).group_by(Item.status).all()
    recent_moves = ItemHistory.query \
        .order_by(ItemHistory.changed_at.desc()).limit(10).all()
    return render_template('stats.html', status_counts=status_counts, recent_moves=recent_moves)


@main.route('/qr/<int:item_id>')
def qr_image(item_id):
    db.get_or_404(Item, item_id)
    url = url_for('main.item_detail', item_id=item_id, _external=True)
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@main.route('/qr/<int:item_id>/download')
def qr_download(item_id):
    item = db.get_or_404(Item, item_id)
    url  = url_for('main.item_detail', item_id=item_id, _external=True)
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    safe_name = item.name.replace(' ', '_').replace('/', '-')
    return send_file(buf, mimetype='image/png', as_attachment=True,
                     download_name=f'qr_{safe_name}.png')


@main.route('/qr/print')
def qr_print():
    items = Item.query.order_by(Item.name).all()
    return render_template('qr_print.html', items=items)


@main.route('/export/csv')
@require_auth
def export_csv():
    items = Item.query.order_by(Item.name).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['ID', 'Название', 'Описание', 'Статус', 'У кого', 'Добавлено', 'Обновлено'])
    for item in items:
        writer.writerow([
            item.id, item.name, item.description or '', item.status, item.holder or '',
            item.created_at.strftime('%d.%m.%Y %H:%M') if item.created_at else '',
            item.updated_at.strftime('%d.%m.%Y %H:%M') if item.updated_at else '',
        ])
    buf.seek(0)
    byte_buf = io.BytesIO(buf.getvalue().encode('utf-8-sig'))
    return send_file(byte_buf, mimetype='text/csv', as_attachment=True,
                     download_name='geekcult_inventory.csv')


@main.route('/admin')
@require_auth
def admin():
    items = Item.query.order_by(Item.updated_at.desc()).all()
    return render_template('admin.html', items=items, statuses=STATUSES)


@main.route('/admin/add', methods=['POST'])
@require_auth
def add_item():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Название не может быть пустым')
        return redirect(url_for('main.admin'))

    status = request.form.get('status', 'Склад ЧелГУ')
    if status not in STATUSES:
        flash('Недопустимый статус')
        return redirect(url_for('main.admin'))

    holder = request.form.get('holder', '').strip() or None
    if status != 'На руках':
        holder = None

    item = Item(
        name=name,
        description=request.form.get('description', ''),
        status=status,
        holder=holder,
    )
    db.session.add(item)
    db.session.commit()

    file = request.files.get('photo')
    if file and file.filename and allowed_file(file.filename):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f'item_{item.id}.{ext}'
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        item.photo = filename
        db.session.commit()

    flash(f'Предмет "{name}" добавлен')
    return redirect(url_for('main.admin'))


@main.route('/admin/update/<int:item_id>', methods=['POST'])
@require_auth
def update_item(item_id):
    item = db.get_or_404(Item, item_id)

    old_status = item.status
    new_status = request.form.get('status', old_status)

    if new_status not in STATUSES:
        flash('Недопустимый статус')
        return redirect(url_for('main.admin'))

    new_holder = request.form.get('holder', '').strip() or None
    if new_status != 'На руках':
        new_holder = None

    note = request.form.get('note', '').strip() or None

    file = request.files.get('photo')
    if file and file.filename and allowed_file(file.filename):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f'item_{item.id}.{ext}'
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        item.photo = filename

    if old_status != new_status or item.holder != new_holder:
        db.session.add(ItemHistory(
            item_id    = item.id,
            old_status = old_status,
            new_status = new_status,
            note       = note,
            changed_by = 'admin',
        ))
        item.status     = new_status
        item.holder     = new_holder
        item.holder_id  = None   # при ручном изменении через админку сбрасываем привязку
        item.updated_at = utc_now()
        db.session.commit()

        holder_str = f' (у {new_holder})' if new_holder else ''
        note_str   = f'\n📝 {note}' if note else ''
        send_telegram(f'📦 <b>{item.name}</b>\n{old_status} → <b>{new_status}{holder_str}</b>{note_str}')
        flash(f'Статус "{item.name}": {old_status} → {new_status}')
    else:
        db.session.commit()
        flash('Изменений нет')

    return redirect(url_for('main.admin'))


@main.route('/admin/delete/<int:item_id>', methods=['POST'])
@require_auth
def delete_item(item_id):
    item = db.get_or_404(Item, item_id)
    name = item.name

    if item.photo:
        photo_path = os.path.join(UPLOAD_FOLDER, item.photo)
        if os.path.exists(photo_path):
            os.remove(photo_path)

    ItemHistory.query.filter_by(item_id=item.id).delete()
    db.session.delete(item)
    db.session.commit()

    flash(f'Предмет "{name}" удалён')
    return redirect(url_for('main.admin'))
