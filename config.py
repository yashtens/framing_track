import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', '579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b')

    # MySQL Database Configuration
    # DB_HOST = os.environ.get('DB_HOST', 'localhost')
    # DB_USER = os.environ.get('DB_USER', 'root')
    # DB_PASSWORD = os.environ.get('DB_PASSWORD', 'yash1947#')
    # DB_NAME = os.environ.get('DB_NAME', 'krishitrack_db')
    # DB_PORT = os.environ.get('DB_PORT', '3306')

    # SQLALCHEMY_DATABASE_URI = (
    #     f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    # )

    # MySQL Database Configuration
    DB_HOST = os.environ.get('DB_HOST', 'mysql.railway.internal')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'sHHJinOioikhTDfisRAyYBSaAoLHnGFU')
    DB_NAME = os.environ.get('DB_NAME', 'railway')
    DB_PORT = os.environ.get('DB_PORT', '3306')

    SQLALCHEMY_DATABASE_URI = (
        "mysql: // root: sHHJinOioikhTDfisRAyYBSaAoLHnGFU @ mysql.railway.internal:3306 / railway"
    )

    # mysql: // root: sHHJinOioikhTDfisRAyYBSaAoLHnGFU @ mysql.railway.internal:3306 / railway
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # Admin credentials (change before production)
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'yash')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'yash1946')