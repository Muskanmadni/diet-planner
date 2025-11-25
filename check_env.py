import sys
print("Python version:", sys.version)

try:
    import psycopg2
    print("SUCCESS: psycopg2 import successful")
except ImportError as e:
    print("ERROR: psycopg2 import failed:", e)

try:
    import flask
    print("SUCCESS: flask import successful")
except ImportError as e:
    print("ERROR: flask import failed:", e)

try:
    import sqlalchemy
    print("SUCCESS: sqlalchemy import successful")
except ImportError as e:
    print("ERROR: sqlalchemy import failed:", e)

try:
    from flask_sqlalchemy import SQLAlchemy
    print("SUCCESS: flask_sqlalchemy import successful")
except ImportError as e:
    print("ERROR: flask_sqlalchemy import failed:", e)

print("\nRequirements file contents:")
with open('requirements.txt', 'r') as f:
    print(f.read())