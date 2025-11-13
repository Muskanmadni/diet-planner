#!/usr/bin/env python3
"""
Direct replacement script for login_required function
"""

# Read the file
with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the specific section to replace in login_required function
# First, let's define the target section that includes the Clerk auth code
start_marker = "        # Check Flask session first (for existing users)\n        if 'user_id' in session and session['user_id'] is not None:\n            return f(*args, **kwargs)\n\n        # Check Clerk authentication"
end_marker = "        return redirect(url_for('login_page'))"

# Find positions
start_pos = content.find(start_marker)
end_pos = content.find(end_marker, start_pos)

if start_pos != -1 and end_pos != -1:
    # Include the return statement in the section to be replaced
    section_to_replace = content[start_pos:end_pos + len("        return redirect(url_for('login_page'))")]
    
    # The replacement will be just the session check and the return statement
    replacement = """        # Check Flask session (for existing users)
        if 'user_id' in session and session['user_id'] is not None:
            return f(*args, **kwargs)

        return redirect(url_for('login_page'))"""
    
    # Perform the replacement
    new_content = content.replace(section_to_replace, replacement)
    
    # Write back the file
    with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("Clerk authentication section removed successfully!")
else:
    print("Could not find the section to replace")
    print("Start marker found:", start_pos != -1)
    print("End marker found:", end_pos != -1)