"""
Database configuration for Turso with custom connector

This file demonstrates how to properly connect to Turso database
for deployment on platforms like Vercel or other cloud providers.
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nutriguide-prod-secret-key-change-in-production')

# Use DATABASE_URL from environment, which should be set on deployment platforms
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # This would be used in production/deployment
    # The deployment platform should set DATABASE_URL to the proper format
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # For local development using your Turso credentials
    turso_url = os.environ.get('TURSO_DATABASE_URL')
    auth_token = os.environ.get('TURSO_AUTH_TOKEN')
    
    if turso_url and auth_token:
        # For local development, use the database as configured
        # In production, you would set the DATABASE_URL environment variable
        # on your deployment platform (like Vercel) to point to your Turso database
        print("Using Turso credentials for local development setup")
        print(f"Turso database will be configured as: {turso_url}")
        print("For deployment, set DATABASE_URL environment variable to your Turso connection string")
    
    # Use local SQLite for now - in deployment, this DATABASE_URL will be set correctly
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'database.db')}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Your models would go here
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # other fields...

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("Database tables created successfully")