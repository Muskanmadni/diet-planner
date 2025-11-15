import sys
import sys
import os
from src.diet_planner.app import app

# Add the project root to the Python path to ensure modules can be found
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


# For Vercel deployment, the WSGI server will look for 'application' as the WSGI callable
application = app

