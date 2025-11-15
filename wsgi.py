import os
from src.diet_planner.app import app
application = app
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8081))
    app.run(host="0.0.0.0", port=port)