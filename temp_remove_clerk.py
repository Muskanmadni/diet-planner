import re

# Read the file
with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Use regex to remove the clerk_auth_required function
pattern = r'def clerk_auth_required\(f\):.*?^    return decorated_function'
import re

# Read the file
with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Filter out the clerk_auth_required function
new_lines = []
in_clerk_func = False

for line in lines:
    if line.strip().startswith('def clerk_auth_required(f):'):
        in_clerk_func = True
    elif in_clerk_func and line.strip() == 'return decorated_function':
        # This is the end of the function, so we skip this line as well
        in_clerk_func = False
        continue
    
    if not in_clerk_func:
        new_lines.append(line)

# Write the modified content back
with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Clerk function removed")