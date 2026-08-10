import os

import qrcode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_qr(item_id, base_url=None):
    base_url = (base_url or os.getenv('BASE_URL', 'http://localhost:5000')).rstrip('/')
    url = base_url + '/item/' + str(item_id)

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)

    filename = 'item_' + str(item_id) + '.png'
    folder = os.path.join(BASE_DIR, 'static', 'qr_codes')
    os.makedirs(folder, exist_ok=True)

    img = qr.make_image(fill_color='black', back_color='white')
    img.save(os.path.join(folder, filename))

    return filename
