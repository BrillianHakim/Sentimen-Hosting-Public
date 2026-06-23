import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-ganti-di-production'
    
    DB_LOCAL   = 'mysql+pymysql://root:@localhost/skripsi_sentimen'
    DB_HOSTING = 'mysql+pymysql://sql12831311:MWP9jQLHfm@sql12.freesqldatabase.com:3306/sql12831311'
    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or DB_LOCAL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production' : ProductionConfig,
    'default'    : DevelopmentConfig
}