#!/usr/bin/env python3
"""Script to remove Clerk authentication code from app.py"""

def remove_clerk_code():
    with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Create a new list to store the filtered lines
    new_lines = []
    skip_section = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if this is the start of the clerk_auth_required function
        if 'def clerk_auth_required(f):' in line:
            # Skip until we find the matching return statement at the same indentation
            level = 0
            while i < len(lines):
                current_line = lines[i]
                indent = len(current_line) - len(current_line.lstrip())
                
                # Count function-like structures to find the end
                if 'def ' in current_line.strip() and indent == 0:
                    break  # Found next function, this function has ended
                    
                # If we find the return statement that ends the function
                if 'return decorated_function' in current_line and indent == 0:
                    i += 1  # Skip this line too
                    break
                i += 1
            continue  # Don't add any lines from the function to new_lines
        
        # Check if this is part of login_required that we want to modify
        elif 'def login_required(f):' in line:
            # We'll need to capture the full function, modify it, and replace it
            function_start = i
            # Find the end of the function
            while i < len(lines) and not (lines[i].strip() and lines[i].strip() != '#' and len(lines[i]) - len(lines[i].lstrip()) == 0):
                i += 1
                if i < len(lines) and lines[i].startswith('    return') or lines[i].startswith('\treturn'):
                    break
            i = function_start  # Reset to start of function to handle it properly
            
            # Collect the function lines
            func_lines = []
            func_indent = len(lines[i]) - len(lines[i].lstrip())
            while i < len(lines):
                current_line = lines[i]
                if not current_line.strip():
                    func_lines.append(current_line)
                    i += 1
                    continue
                current_indent = len(current_line) - len(current_line.lstrip())
                # If we find a line with same or less indentation and not part of function, we're done
                if current_indent <= func_indent and current_line.strip() and not current_line.strip().startswith('#'):
                    break
                func_lines.append(current_line)
                if 'return redirect' in current_line and 'login_page' in current_line:
                    break
                i += 1
            
            # Process the function to remove Clerk authentication part
            cleaned_func = []
            in_clerk_section = False
            for func_line in func_lines:
                if '# Check Clerk authentication' in func_line:
                    in_clerk_section = True
                elif in_clerk_section and 'return redirect' in func_line:
                    in_clerk_section = False
                    cleaned_func.append(func_line)
                elif not in_clerk_section:
                    cleaned_func.append(func_line)
            
            new_lines.extend(cleaned_func)
            continue  # Skip to next iteration to continue processing
        
        # Remove Clerk-related code in current_user function
        elif '# Check if this is a Clerk-authenticated user' in line:
            # Skip this line and all Clerk-related processing until we hit the next main condition
            while i < len(lines) and not ('if not user_id:' in lines[i] and 'return jsonify' in lines[i+1] if i+1 < len(lines) else False):
                i += 1
            continue
            
        else:
            new_lines.append(line)
            i += 1
    
    # Write the modified content back
    with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

if __name__ == "__main__":
    remove_clerk_code()
    print("Clerk authentication code removed from app.py")