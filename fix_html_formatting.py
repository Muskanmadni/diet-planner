#!/usr/bin/env python3
"""
Script to fix HTML formatting that may have been affected during processing
"""

import re


def pretty_print_html(file_path):
    """Format HTML with proper indentation"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Store the original length to check if we changed anything
    original_length = len(content)
    
    # A simple HTML formatter that adds basic structure
    # This is a simplified approach for restoring basic formatting
    
    # First, let's try to add basic newlines around tags
    # Add newlines before closing tags
    content = re.sub(r'>\s*<', '>\n<', content)
    
    # Then format with basic indentation (this is a simplified approach)
    lines = content.split('\n')
    formatted_lines = []
    indent_level = 0
    indent_size = 2
    
    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue
            
        # Reduce indent for closing tags
        if stripped_line.startswith('</'):
            indent_level = max(0, indent_level - 1)
            
        # Add properly indented line
        if stripped_line:
            formatted_lines.append(' ' * (indent_level * indent_size) + stripped_line)
            
        # Increase indent for opening tags (but not self-closing)
        if stripped_line.startswith('<') and not stripped_line.startswith('</') and not stripped_line.endswith('/>'):
            # Check if it's a tag that should increase indentation (not self-closing)
            tag_name = re.match(r'<(\w+)', stripped_line)
            if tag_name:
                tag = tag_name.group(1).lower()
                # Common tags that shouldn't increase indentation (self-closing)
                if tag not in ['br', 'hr', 'img', 'input', 'meta', 'link']:
                    indent_level += 1
    
    # Join the formatted lines
    formatted_content = '\n'.join(formatted_lines)
    
    # Write back to file only if we changed something
    if len(formatted_content) > len(content) / 2:  # Basic check to avoid empty results
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
        
        print(f"Formatted {file_path} - {len(formatted_content)} lines after formatting")
        return True
    else:
        print(f"No changes made to {file_path} - content appears problematic")
        return False


def main():
    # HTML files to process
    html_files = [
        "src/diet_planner/diet_plan.html",
        "src/diet_planner/meal_plan.html",
        "src/diet_planner/dashboard.html", 
        "src/diet_planner/recipes.html",
        "src/diet_planner/shopping_list.html",
        "src/diet_planner/settings.html",
    ]
    
    project_base = "D:/python/Agentic-Ai/Quater4/projects/diet-planner/"
    
    for html_file in html_files:
        file_path = project_base + html_file
        try:
            pretty_print_html(file_path)
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")


if __name__ == "__main__":
    main()