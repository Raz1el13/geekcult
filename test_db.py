import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    print("✅ Подключение к PostgreSQL успешно!")
    conn.close()
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")