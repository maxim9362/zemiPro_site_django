import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")

# Формируем URL из отдельных переменных
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_HOST = os.getenv("DB_HOST", "db")  # "db" - это имя контейнера с базой

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
#DATABASE_URL = "postgresql://postgres:00000000@localhost:5432/mydb" # ноут
