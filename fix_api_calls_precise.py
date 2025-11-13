import re

def fix_api_calls():
    # Read the file content
    with open('src/diet_planner/app.py', 'r', encoding='utf-8') as file:
        content = file.read()

    # Fix the first occurrence in the general diet plan endpoint
    # First, find the correct pattern around the diet plan endpoint (around line 1390-1400)
    
    # The original problem area was around the diet plan generation
    pattern_to_fix = r'system_instruction = "You are an expert Pakistani nutritionist\. Generate a comprehensive, healthy weekly diet plan with traditional Pakistani foods\. Consider dietary restrictions and medical conditions\. Respond in a structured format with clear meal plans and nutritional information\."\s*\n\s*\n\s*response = model\.generate_content\(f"\{system_instruction\} \{prompt\}"\)\s*\n\s*\n\s*# Extract the response text\s*\n\s*diet_plan_text = response\.text if response and hasattr\(response, \'text\'\) else "Unable to generate diet plan\. Please try again later\."\s*\n\s*'
    
    # Replace with the fixed version
    replacement = '''system_instruction = "You are an expert Pakistani nutritionist. Generate a comprehensive, healthy weekly diet plan with traditional Pakistani foods. Consider dietary restrictions and medical conditions. Respond in a structured format with clear meal plans and nutritional information."

                try:
                    response = model.generate_content(f"{system_instruction} {prompt}")
                    
                    # Extract the response text
                    if response and hasattr(response, 'text'):
                        diet_plan_text = response.text
                    elif hasattr(response, '_result') and response._result and hasattr(response._result, 'candidates') and response._result.candidates:
                        # Handle different response structure if needed
                        diet_plan_text = response._result.candidates[0].content.parts[0].text if response._result.candidates[0].content.parts else "Unable to generate diet plan. Please try again later."
                    else:
                        diet_plan_text = "Unable to generate diet plan. Please try again later."
                except Exception as ai_error:
                    print(f"Error calling AI model: {ai_error}")
                    diet_plan_text = "Error generating diet plan. Please try again later."

                # Format the response
                formatted_plan = format_diet_plan_response(diet_plan_text)'''

    # Use re.sub to replace the pattern
    content = re.sub(pattern_to_fix, replacement, content, flags=re.DOTALL)

    # Write the updated content back to the file
    with open('src/diet_planner/app.py', 'w', encoding='utf-8') as file:
        file.write(content)

    print("File updated successfully!")

if __name__ == "__main__":
    fix_api_calls()