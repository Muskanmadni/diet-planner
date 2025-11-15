def main() -> None:
    print("Hello from diet-planner!")

def start():
    # Import here to avoid circular dependency
    from .app import app
    # Run the Flask app
    app.run(debug=True, host='127.0.0.1', port=5000)

__all__ = ['main', 'start']
