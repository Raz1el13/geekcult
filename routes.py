import io
import os
import csv
import qrcode
import requests
from functools import wraps
from werkzeug.utils import secure_filename

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, send_file, Response, session)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func

from models import db, Item, ItemHistory, User, STATUSES, utc_now

main = Blueprint('main', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'photos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

MIME_BY_EXT = {
    'png':  'image/png',
    'jpg':  'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
}

def allowed_file(f):
    return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_photo(item, file):
    """Кладёт картинку прямо в БД — переживает передеплой."""
    if not (file and file.filename and allowed_file(file.filename)):
        return False
    ext = file.filename.rsplit('.', 1)[1].lower()
    item.photo_data = file.read()
    item.photo_mime = MIME_BY_EXT.get(ext, 'image/jpeg')
    return True

def require_auth(f):
    """Доступ только для админов — по флагу is_admin у залогиненного юзера."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Войдите в аккаунт администратора')
            return redirect(url_for('main.login', next=request.path))
        if not current_user.is_admin:
            flash('Раздел доступен только администраторам')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated

def send_telegram(text):
    token   = os.getenv('TG_BOT_TOKEN')
    chat_id = os.getenv('TG_CHAT_ID')
    if not token or not chat_id:
        return
    try:
        requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                      json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
                      timeout=5)
    except Exception:
        pass

# ── Авторизация ───────────────────────────────────────────────────────────────

@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password2= request.form.get('password2', '')

        if not name or not email or not password:
            flash('Заполните все поля')
            return render_template('register.html')

        if len(password) < 6:
            flash('Пароль минимум 6 символов')
            return render_template('register.html', name=name, email=email)

        if password != password2:
            flash('Пароли не совпадают')
            return render_template('register.html', name=name, email=email)

        if User.query.filter_by(email=email).first():
            flash('Этот email уже зарегистрирован')
            return render_template('register.html', name=name)

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash(f'Добро пожаловать, {user.name}!')
        return redirect(url_for('main.index'))

    return render_template('register.html')


@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Неверный email или пароль')
            return render_template('login.html', email=email)

        login_user(user, remember=remember)
        flash(f'Привет, {user.name}!')

        next_url = request.args.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('main.index'))

    return render_template('login.html')


@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из аккаунта')
    return redirect(url_for('main.index'))


@main.route('/profile')
@login_required
def profile():
    my_items = Item.query.filter_by(holder_id=current_user.id).all()

    # История: что брал раньше (записи о взятии этим пользователем)
    history = ItemHistory.query\
        .filter_by(user_id=current_user.id, new_status='На руках')\
        .order_by(ItemHistory.changed_at.desc())\
        .limit(20).all()

    return render_template('profile.html', my_items=my_items, history=history)


# ── Бронирование ──────────────────────────────────────────────────────────────

@main.route('/item/<int:item_id>/book', methods=['POST'])
@login_required
def book_item(item_id):
    item = db.get_or_404(Item, item_id)

    if item.status == 'На руках':
        flash(f'«{item.name}» уже на руках')
        return redirect(url_for('main.item_detail', item_id=item_id))

    old_status = item.status
    item.status    = 'На руках'
    item.holder    = current_user.name
    item.holder_id = current_user.id
    item.updated_at = utc_now()

    db.session.add(ItemHistory(
        item_id=item.id,
        old_status=old_status,
        new_status='На руках',
        user_id=current_user.id,
        note=f'Забронировано пользователем {current_user.name}'
    ))
    db.session.commit()

    send_telegram(f'📦 <b>{item.name}</b>\n{old_status} → <b>На руках</b> (у {current_user.name})')
    flash(f'«{item.name}» забронирован и теперь у вас на руках')
    return redirect(url_for('main.profile'))


@main.route('/item/<int:item_id>/return', methods=['POST'])
@login_required
def return_item(item_id):
    item = db.get_or_404(Item, item_id)

    if item.holder_id != current_user.id:
        flash('Этот предмет не у вас')
        return redirect(url_for('main.profile'))

    old_status = item.status
    # Возвращаем на предыдущее место из истории
    prev = ItemHistory.query.filter_by(item_id=item.id)\
        .filter(ItemHistory.new_status == 'На руках')\
        .order_by(ItemHistory.changed_at.desc()).first()
    return_status = prev.old_status if prev and prev.old_status else 'Склад ЧелГУ'

    item.status     = return_status
    item.holder     = None
    item.holder_id  = None
    item.updated_at = utc_now()

    db.session.add(ItemHistory(
        item_id=item.id,
        old_status=old_status,
        new_status=return_status,
        user_id=current_user.id,
        note=f'Возвращено пользователем {current_user.name}'
    ))
    db.session.commit()

    flash(f'«{item.name}» возвращён')
    return redirect(url_for('main.profile'))


# ── Публичные страницы ────────────────────────────────────────────────────────

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

    recent_moves = ItemHistory.query\
        .order_by(ItemHistory.changed_at.desc()).limit(10).all()

    total_items  = Item.query.count()
    total_users  = User.query.count()
    total_moves  = ItemHistory.query.count()
    on_hands     = Item.query.filter_by(status='На руках').count()

    # Топ-5 самых востребованных предметов
    top_items = db.session.query(
        Item.name, func.count(ItemHistory.id).label('cnt')
    ).join(ItemHistory, ItemHistory.item_id == Item.id)\
     .filter(ItemHistory.new_status == 'На руках')\
     .group_by(Item.id, Item.name)\
     .order_by(func.count(ItemHistory.id).desc())\
     .limit(5).all()

    # Топ-5 самых активных пользователей
    top_users = db.session.query(
        User.name, func.count(ItemHistory.id).label('cnt')
    ).join(ItemHistory, ItemHistory.user_id == User.id)\
     .filter(ItemHistory.new_status == 'На руках')\
     .group_by(User.id, User.name)\
     .order_by(func.count(ItemHistory.id).desc())\
     .limit(5).all()

    return render_template('stats.html',
                           status_counts=status_counts,
                           recent_moves=recent_moves,
                           total_items=total_items,
                           total_users=total_users,
                           total_moves=total_moves,
                           on_hands=on_hands,
                           top_items=top_items,
                           top_users=top_users)


@main.route('/photo/<int:item_id>')
def item_photo(item_id):
    item = db.get_or_404(Item, item_id)
    if not item.photo_data:
        return Response(status=404)
    return send_file(io.BytesIO(item.photo_data),
                     mimetype=item.photo_mime or 'image/jpeg')


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
        writer.writerow([item.id, item.name, item.description or '', item.status,
                         item.holder or '',
                         item.created_at.strftime('%d.%m.%Y %H:%M') if item.created_at else '',
                         item.updated_at.strftime('%d.%m.%Y %H:%M') if item.updated_at else ''])
    buf.seek(0)
    byte_buf = io.BytesIO(buf.getvalue().encode('utf-8-sig'))
    return send_file(byte_buf, mimetype='text/csv', as_attachment=True,
                     download_name='geekcult_inventory.csv')


# ── Админ-панель ──────────────────────────────────────────────────────────────

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

    item = Item(name=name, description=request.form.get('description', ''),
                status=status, holder=holder)
    db.session.add(item)
    db.session.commit()

    file = request.files.get('photo')
    if save_photo(item, file):
        db.session.commit()

    flash(f'Предмет «{name}» добавлен')
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

    # Название и описание
    new_name = request.form.get('name', '').strip()
    if new_name:
        item.name = new_name
    item.description = request.form.get('description', '').strip() or None

    file = request.files.get('photo')
    save_photo(item, file)

    if old_status != new_status or item.holder != new_holder:
        db.session.add(ItemHistory(item_id=item.id, old_status=old_status,
                                   new_status=new_status, note=note))
        item.status     = new_status
        item.holder     = new_holder
        item.holder_id  = None
        item.updated_at = utc_now()
        db.session.commit()
        flash(f'Статус «{item.name}»: {old_status} → {new_status}')
    else:
        item.updated_at = utc_now()
        db.session.commit()
        flash(f'Предмет «{item.name}» обновлён')

    return redirect(url_for('main.admin'))


@main.route('/admin/delete/<int:item_id>', methods=['POST'])
@require_auth
def delete_item(item_id):
    item = db.get_or_404(Item, item_id)
    name = item.name
    ItemHistory.query.filter_by(item_id=item.id).delete()
    db.session.delete(item)
    db.session.commit()
    flash(f'Предмет «{name}» удалён')
    return redirect(url_for('main.admin'))
