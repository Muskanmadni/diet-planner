from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

# Test database configuration similar to your app
database_url = "postgresql://019aaf22-80a9-7236-83f8-f67eecf76bdb:478df69b-3b78-46e5-b85f-0859afb2926f@us-west-2.db.thenile.dev:5432/nutridb"

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

try:
    db = SQLAlchemy(app)
    print("SQLAlchemy initialized successfully with PostgreSQL URL")
    print("No psycopg2 import error!")
except Exception as e:
    print(f"Error initializing SQLAlchemy: {e}")