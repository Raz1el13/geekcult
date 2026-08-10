import io
import os
from functools import wraps

import qrcode
from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import func, or_

from models import (
    STATUS_TAKEN,
    STATUSES,
    Booking,
    Item,
    ItemHistory,
    User,
    db,
    utc_now,
)
from utils import generate_qr


main = Blueprint('main', __name__)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated and current_user.is_admin:
            return f(*args, **kwargs)

        auth = request.authorization
        login = os.getenv('ADMIN_LOGIN', 'admin')
        password = os.getenv('ADMIN_PASSWORD', 'geekcult2026')

        if auth and auth.username == login and auth.password == password:
            return f(*args, **kwargs)

        return Response(
            'Нужна авторизация',
            401,
            {'WWW-Authenticate': 'Basic realm="Admin"'}
        )

    return decorated


@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        errors = []

        if len(username) < 3:
            errors.append('Логин — минимум 3 символа')

        if not full_name:
            errors.append('Укажите имя и фамилию')

        if len(password) < 6:
            errors.append('Пароль — минимум 6 символов')

        if password != password2:
            errors.append('Пароли не совпадают')

        if User.query.filter_by(username=username).first():
            errors.append('Такой логин уже занят')

        if errors:
            for e in errors:
                flash(e, 'danger')

            return render_template(
                'register.html',
                username=username,
                full_name=full_name
            )

        user = User(
            username=username,
            full_name=full_name
        )

        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        login_user(user)

        flash(
            'Добро пожаловать в ГикКульт, '
            + user.display_name
            + '!',
            'success'
        )

        return redirect(url_for('main.index'))

    return render_template('register.html')


@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Неверный логин или пароль', 'danger')

            return render_template(
                'login.html',
                username=username
            )

        login_user(
            user,
            remember=bool(request.form.get('remember'))
        )

        flash(
            'Вы вошли как ' + user.display_name,
            'success'
        )

        next_url = request.args.get('next')

        if next_url and next_url.startswith('/'):
            return redirect(next_url)

        return redirect(url_for('main.index'))

    return render_template('login.html')


@main.route('/logout')
@login_required
def logout():
    logout_user()

    flash(
        'Вы вышли из аккаунта',
        'success'
    )

    return redirect(url_for('main.index'))


@main.route('/')
def index():
    # Поисковая строка
    search_query = request.args.get('q', '').strip()

    # Фильтр по статусу / местонахождению
    status_filter = request.args.get('status', '').strip()

    query = Item.query

    # Поиск по названию, описанию, статусу и держателю
    if search_query:
        search_pattern = f'%{search_query}%'

        query = query.filter(
            or_(
                Item.name.ilike(search_pattern),
                Item.description.ilike(search_pattern),
                Item.status.ilike(search_pattern),
                Item.holder.ilike(search_pattern),
            )
        )

    # Фильтр по конкретному статусу
    if status_filter:
        query = query.filter(
            Item.status == status_filter
        )

    items = (
        query
        .order_by(Item.updated_at.desc())
        .all()
    )

    return render_template(
        'index.html',
        items=items,
        statuses=STATUSES,
        active_status=status_filter,
        search_query=search_query,
    )


@main.route('/item/<int:item_id>')
def item_detail(item_id):
    item = db.get_or_404(
        Item,
        item_id
    )

    return render_template(
        'item.html',
        item=item
    )


@main.route('/item/<int:item_id>/book', methods=['POST'])
@login_required
def book_item(item_id):
    query = Item.query.filter_by(
        id=item_id
    )

    if db.engine.dialect.name == 'postgresql':
        query = query.with_for_update()

    item = query.first()

    if item is None:
        flash(
            'Предмет не найден',
            'danger'
        )

        return redirect(
            url_for('main.index')
        )

    if item.status == STATUS_TAKEN:
        db.session.rollback()

        flash(
            'Увы, «'
            + item.name
            + '» уже на руках у '
            + (item.holder or 'кого-то'),
            'danger'
        )

        return redirect(
            request.referrer
            or url_for('main.index')
        )

    old_status = item.status

    db.session.add(
        Booking(
            item_id=item.id,
            user_id=current_user.id,
            prev_status=old_status
        )
    )

    db.session.add(
        ItemHistory(
            item_id=item.id,
            old_status=old_status,
            new_status=STATUS_TAKEN,
            user_id=current_user.id
        )
    )

    item.status = STATUS_TAKEN
    item.holder = current_user.display_name
    item.holder_user_id = current_user.id
    item.updated_at = utc_now()

    db.session.commit()

    flash(
        '«'
        + item.name
        + '» теперь у вас на руках',
        'success'
    )

    return redirect(
        request.referrer
        or url_for('main.my_items')
    )


@main.route('/item/<int:item_id>/return', methods=['POST'])
@login_required
def return_item(item_id):
    item = db.get_or_404(
        Item,
        item_id
    )

    if not (
        item.holder_user_id == current_user.id
        or current_user.is_admin
    ):
        flash(
            'Эта вещь взята не вами',
            'danger'
        )

        return redirect(
            request.referrer
            or url_for('main.index')
        )

    booking = (
        Booking.query
        .filter_by(
            item_id=item.id,
            returned_at=None
        )
        .order_by(
            Booking.taken_at.desc()
        )
        .first()
    )

    new_status = (
        booking.prev_status
        if booking and booking.prev_status
        else STATUSES[0]
    )

    if booking:
        booking.returned_at = utc_now()

    db.session.add(
        ItemHistory(
            item_id=item.id,
            old_status=item.status,
            new_status=new_status,
            user_id=current_user.id
        )
    )

    item.status = new_status
    item.holder = None
    item.holder_user_id = None
    item.updated_at = utc_now()

    db.session.commit()

    flash(
        '«'
        + item.name
        + '» возвращена: '
        + new_status,
        'success'
    )

    return redirect(
        request.referrer
        or url_for('main.my_items')
    )


@main.route('/my')
@login_required
def my_items():
    items = (
        Item.query
        .filter_by(
            holder_user_id=current_user.id
        )
        .order_by(
            Item.updated_at.desc()
        )
        .all()
    )

    history = (
        Booking.query
        .filter(
            Booking.user_id == current_user.id,
            Booking.returned_at.isnot(None)
        )
        .order_by(
            Booking.returned_at.desc()
        )
        .limit(20)
        .all()
    )

    return render_template(
        'my_items.html',
        items=items,
        history=history
    )


@main.route('/stats')
def stats():
    status_counts = (
        db.session.query(
            Item.status,
            func.count(Item.id)
        )
        .group_by(Item.status)
        .all()
    )

    recent_moves = (
        ItemHistory.query
        .order_by(
            ItemHistory.changed_at.desc()
        )
        .limit(10)
        .all()
    )

    return render_template(
        'stats.html',
        status_counts=status_counts,
        recent_moves=recent_moves,
        total=Item.query.count(),
        users_count=User.query.count()
    )


@main.route('/admin')
@require_auth
def admin():
    items = (
        Item.query
        .order_by(
            Item.updated_at.desc()
        )
        .all()
    )

    users = (
        User.query
        .order_by(
            User.created_at.desc()
        )
        .all()
    )

    return render_template(
        'admin.html',
        items=items,
        statuses=STATUSES,
        users=users
    )


@main.route('/admin/add', methods=['POST'])
@require_auth
def add_item():
    name = request.form.get(
        'name',
        ''
    ).strip()

    if not name:
        flash(
            'Название не может быть пустым',
            'danger'
        )

        return redirect(
            url_for('main.admin')
        )

    status = request.form.get(
        'status',
        STATUSES[0]
    )

    holder = (
        request.form.get(
            'holder',
            ''
        ).strip()
        or None
    )

    if status != STATUS_TAKEN:
        holder = None

    item = Item(
        name=name,
        description=request.form.get(
            'description',
            ''
        ),
        status=status,
        holder=holder
    )

    db.session.add(item)
    db.session.commit()

    item.qr_filename = generate_qr(
        item.id
    )

    db.session.commit()

    flash(
        'Предмет «'
        + name
        + '» добавлен',
        'success'
    )

    return redirect(
        url_for('main.admin')
    )


@main.route('/admin/update/<int:item_id>', methods=['POST'])
@require_auth
def update_item(item_id):
    item = db.get_or_404(
        Item,
        item_id
    )

    old_status = item.status

    new_status = request.form.get(
        'status',
        old_status
    )

    new_holder = (
        request.form.get(
            'holder',
            ''
        ).strip()
        or None
    )

    if new_status != STATUS_TAKEN:
        new_holder = None

    if (
        old_status != new_status
        or item.holder != new_holder
    ):
        db.session.add(
            ItemHistory(
                item_id=item.id,
                old_status=old_status,
                new_status=new_status
            )
        )

        if new_status != STATUS_TAKEN:
            for booking in (
                Booking.query
                .filter_by(
                    item_id=item.id,
                    returned_at=None
                )
                .all()
            ):
                booking.returned_at = utc_now()

            item.holder_user_id = None

        item.status = new_status
        item.holder = new_holder
        item.updated_at = utc_now()

        db.session.commit()

        flash(
            'Статус «'
            + item.name
            + '»: '
            + old_status
            + ' -> '
            + new_status,
            'success'
        )

    else:
        flash(
            'Изменений нет',
            'warning'
        )

    return redirect(
        url_for('main.admin')
    )


@main.route('/qr/<int:item_id>')
def qr_image(item_id):
    db.get_or_404(
        Item,
        item_id
    )

    url = url_for(
        'main.item_detail',
        item_id=item_id,
        _external=True
    )

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )

    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color='black',
        back_color='white'
    )

    buf = io.BytesIO()

    img.save(
        buf,
        format='PNG'
    )

    buf.seek(0)

    return send_file(
        buf,
        mimetype='image/png'
    )