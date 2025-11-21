import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

# Get Turso credentials
turso_url = os.environ.get('TURSO_DATABASE_URL')
auth_token = os.environ.get('TURSO_AUTH_TOKEN')

if turso_url and auth_token:
    # Format the URL properly for libsql
    clean_url = turso_url.replace('libsql://', '')
    database_url = f"libsql://{clean_url}?auth_token={auth_token}"
    
    print(f"Attempting to connect to Turso database...")
    print(f"Database URL: {database_url.replace(auth_token, '***HIDDEN***')}")
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        # Test the connection
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("✅ Successfully connected to Turso database!")
            print(f"✅ Connection test result: {result.fetchone()}")
            
            # Try to create a simple test table
            connection.execute(text("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, name TEXT);"))
            connection.commit()
            print("✅ Test table created successfully!")
            
    except Exception as e:
        print(f"❌ Error connecting to Turso database: {e}")
        print("ℹ️  Make sure you have installed the required dependencies: pip install libsql-client sqlalchemy")

else:
    print("❌ Turso credentials not found in environment variables")
    print(f"ℹ️  TURSO_DATABASE_URL: {'Found' if turso_url else 'Not found'}")
    print(f"ℹ️  TURSO_AUTH_TOKEN: {'Found' if auth_token else 'Not found (but will be hidden)'}")