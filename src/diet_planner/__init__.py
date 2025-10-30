from .app import app

def main() -> None:
    print("Hello from diet-planner!")
    
def start():
    # Run the Flask app
    app.run(debug=True, host='127.0.0.1', port=5000)

__all__ = ['project', 'main', 'start']
