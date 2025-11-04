import sqlite3

# Connect to the database
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:", tables)

for table_name in tables:
    table = table_name[0]
    print(f"\nStructure of table '{table}':")
    
    # Get table info
    cursor.execute(f"PRAGMA table_info('{table}');")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col}")
    
    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM '{table}';")
    count = cursor.fetchone()[0]
    print(f"  Row count: {count}")

conn.close()