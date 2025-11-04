import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from diet_planner.app import app, model

print("Checking if app loads correctly...")

# Test model configuration
if model:
    print("[OK] Gemini model is configured and available")
else:
    print("[ERROR] Gemini model is NOT available - this could be why diet plans aren't generating")

# Check if the app routes are properly set up
with app.app_context():
    print("\nRegistered routes:")
    for rule in app.url_map.iter_rules():
        if 'diet' in str(rule) or 'plan' in str(rule).lower():
            print(f"  {rule.rule} -> {rule.endpoint}")

print("\nApplication ready!")