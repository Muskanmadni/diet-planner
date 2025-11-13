def fix_corrupted_app():
    with open('src/diet_planner/app.py', 'r', encoding='utf-8') as file:
        lines = file.readlines()
    
    # Find the correct location around the diet plan endpoint
    # Look for the specific pattern we want to fix
    
    # Find the beginning of the problematic section
    target_found = False
    for i, line in enumerate(lines):
        if 'system_instruction = "You are an expert Pakistani nutritionist.' in line:
            target_found = True
            # Find the next few lines to locate the exact area
            start_index = i
            break
    
    if not target_found:
        print("Target section not found")
        return

    # Now find the problematic area - where multiple duplicate "try:" statements appear
    # Look for the area that has multiple nested try statements
    
    fixed_lines = []
    i = 0
    while i < len(lines):
        # If we're at the problematic section, replace it
        if (i >= start_index and 
            i < start_index + 20 and 
            'response = model.generate_content(f"{system_instruction} {prompt}")' in lines[i]):
            
            # Find the correct section to replace
            # Look for the first occurrence of the problematic pattern with duplicate try statements
            if i + 3 < len(lines) and 'try:' in lines[i] and 'try:' in lines[i+1]:
                print(f"Found duplicate try blocks at line {i+1}")
                
                # Replace the entire problematic section with the correct one
                fixed_section = [
                    '                try:\n',
                    '                    response = model.generate_content(f"{system_instruction} {prompt}")\n',
                    '                    \n',
                    '                    # Extract the response text\n',
                    '                    if response and hasattr(response, \'text\'):\n',
                    '                        diet_plan_text = response.text\n',
                    '                    elif hasattr(response, \'_result\') and response._result and hasattr(response._result, \'candidates\') and response._result.candidates:\n',
                    '                        # Handle different response structure if needed\n',
                    '                        diet_plan_text = response._result.candidates[0].content.parts[0].text if response._result.candidates[0].content.parts else "Unable to generate diet plan. Please try again later."\n',
                    '                    else:\n',
                    '                        diet_plan_text = "Unable to generate diet plan. Please try again later."\n',
                    '                except Exception as ai_error:\n',
                    '                    print(f"Error calling AI model: {ai_error}")\n',
                    '                    diet_plan_text = "Error generating diet plan. Please try again later."\n',
                    '\n',
                    '                # Format the response\n',
                    '                formatted_plan = format_diet_plan_response(diet_plan_text)\n'
                ]
                
                fixed_lines.extend(fixed_section)
                
                # Skip the problematic duplicate lines
                j = i
                while j < len(lines) and ('alternatives_text' in lines[j] or 'shopping_list_text' in lines[j] or 'recipe_suggestions_text' in lines[j]):
                    j += 1
                i = j
            else:
                fixed_lines.append(lines[i])
                i += 1
        else:
            fixed_lines.append(lines[i])
            i += 1
    
    with open('src/diet_planner/app.py', 'w', encoding='utf-8') as file:
        file.writelines(fixed_lines)
    
    print("Fixed the duplicate try blocks")

if __name__ == "__main__":
    fix_corrupted_app()