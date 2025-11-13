import re

# Read the file
with open('src/diet_planner/app.py', 'r', encoding='utf-8') as file:
    content = file.read()

# Remove the function including decorator and comment
pattern = r'# FIXED: Weekly Meal Plan Generator \(No Repeated Days!\) - Now Available to All Users\n@app\.route\(\'/api/diet-plan\', methods=\[\'POST\'\]\)\s+def generate_weekly_meal_plan\(\):\s+.*?\n\s*except Exception as e:\s+return jsonify\({\'error\': str\(e\)}\), 500\n'
content = re.sub(pattern, '', content, flags=re.DOTALL)

# Write back to file
with open('src/diet_planner/app.py', 'w', encoding='utf-8') as file:
    file.write(content)

print("Function removed successfully.")