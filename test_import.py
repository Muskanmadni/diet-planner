try:
    import psycopg2
    print("psycopg2 imported successfully")
except ImportError as e:
    print(f"Failed to import psycopg2: {e}")
    
try:
    import psycopg2_binary
    print("psycopg2_binary imported successfully")
except ImportError as e:
    print(f"Failed to import psycopg2_binary: {e}")

try:
    import psycopg2._psycopg
    print("psycopg2._psycopg imported successfully")
except ImportError as e:
    print(f"Failed to import psycopg2._psycopg: {e}")