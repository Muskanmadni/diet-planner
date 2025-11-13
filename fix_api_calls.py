import re

def fix_api_calls():
    # Read the file content
    with open('src/diet_planner/app.py', 'r', encoding='utf-8') as file:
        content = file.read()

    # Fix the first occurrence in the general diet plan endpoint
    original_code_1 = '''                response = model.generate_content(f"{system_instruction} {prompt}")

                # Extract the response text
                diet_plan_text = response.text if response and hasattr(response, 'text') else "Unable to generate diet plan. Please try again later."'''

    new_code_1 = '''                try:
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
                    diet_plan_text = "Error generating diet plan. Please try again later."'''

    # Replace the first occurrence
    content = content.replace(original_code_1, new_code_1)

    # Fix the second occurrence in the premium diet plan endpoint (around line 1051)
    original_code_2 = '''        response = model.generate_content(f"{system_instruction} {prompt}")

        # Extract the response text
        diet_plan_text = response.text if response and hasattr(response, 'text') else "Unable to generate diet plan. Please try again later."'''

    new_code_2 = '''        try:
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
            diet_plan_text = "Error generating diet plan. Please try again later."'''

    # Replace the second occurrence
    content = content.replace(original_code_2, new_code_2)

    # Fix the third occurrence in the meal plan endpoint (around line 726)
    original_code_3 = '''        response = model.generate_content(f"{system_instruction} {prompt}")

        # Extract the response text and try to parse as JSON
        meal_plan_text = response.text'''

    new_code_3 = '''        try:
            response = model.generate_content(f"{system_instruction} {prompt}")
            
            # Extract the response text and try to parse as JSON
            if response and hasattr(response, 'text'):
                meal_plan_text = response.text
            elif hasattr(response, '_result') and response._result and hasattr(response._result, 'candidates') and response._result.candidates:
                # Handle different response structure if needed
                meal_plan_text = response._result.candidates[0].content.parts[0].text if response._result.candidates[0].content.parts else "Unable to generate meal plan. Please try again later."
            else:
                meal_plan_text = "Unable to generate meal plan. Please try again later."
        except Exception as ai_error:
            print(f"Error calling AI model: {ai_error}")
            meal_plan_text = "Error generating meal plan. Please try again later."'''

    # Replace the third occurrence
    content = content.replace(original_code_3, new_code_3)

    # Fix the recipe suggestions endpoint (around line 881)
    original_code_4 = '''        response = model.generate_content(f"{system_instruction} {prompt}")'''

    new_code_4 = '''        try:
            response = model.generate_content(f"{system_instruction} {prompt}")
            
            # Extract the response text
            if response and hasattr(response, 'text'):
                recipe_suggestions_text = response.text
            elif hasattr(response, '_result') and response._result and hasattr(response._result, 'candidates') and response._result.candidates:
                # Handle different response structure if needed
                recipe_suggestions_text = response._result.candidates[0].content.parts[0].text if response._result.candidates[0].content.parts else "Unable to generate recipe suggestions. Please try again later."
            else:
                recipe_suggestions_text = "Unable to generate recipe suggestions. Please try again later."
        except Exception as ai_error:
            print(f"Error calling AI model for recipe suggestions: {ai_error}")
            recipe_suggestions_text = "Error generating recipe suggestions. Please try again later."'''

    # Replace the fourth occurrence
    content = content.replace(original_code_4, new_code_4)

    # Fix the shopping list endpoint (around line 915)
    original_code_5 = '''        response = model.generate_content(f"{system_instruction} {prompt}")'''

    new_code_5 = '''        try:
            response = model.generate_content(f"{system_instruction} {prompt}")
            
            # Extract the response text
            if response and hasattr(response, 'text'):
                shopping_list_text = response.text
            elif hasattr(response, '_result') and response._result and hasattr(response._result, 'candidates') and response._result.candidates:
                # Handle different response structure if needed
                shopping_list_text = response._result.candidates[0].content.parts[0].text if response._result.candidates[0].content.parts else "Unable to generate shopping list. Please try again later."
            else:
                shopping_list_text = "Unable to generate shopping list. Please try again later."
        except Exception as ai_error:
            print(f"Error calling AI model for shopping list: {ai_error}")
            shopping_list_text = "Error generating shopping list. Please try again later."'''

    # Replace the fifth occurrence
    content = content.replace(original_code_5, new_code_5)

    # Fix the meal swap endpoint (around line 1567)
    original_code_6 = '''        response = model.generate_content(f"{system_instruction} {prompt}")'''

    new_code_6 = '''        try:
            response = model.generate_content(f"{system_instruction} {prompt}")
            
            # Extract the response text
            if response and hasattr(response, 'text'):
                alternatives_text = response.text
            elif hasattr(response, '_result') and response._result and hasattr(response._result, 'candidates') and response._result.candidates:
                # Handle different response structure if needed
                alternatives_text = response._result.candidates[0].content.parts[0].text if response._result.candidates[0].content.parts else "Unable to generate meal alternatives. Please try again later."
            else:
                alternatives_text = "Unable to generate meal alternatives. Please try again later."
        except Exception as ai_error:
            print(f"Error calling AI model for meal alternatives: {ai_error}")
            alternatives_text = "Error generating meal alternatives. Please try again later."'''

    # Replace the sixth occurrence
    content = content.replace(original_code_6, new_code_6)

    # Fix the chatbot endpoint (around line 407) - this one has a slightly different structure
    original_code_7 = '''            response = model.generate_content(
                f"{system_instruction} User ka sawal: {user_message}"
            )

            # Extract the response text
            bot_response = response.text if response and hasattr(response, 'text') else "Maaf kijiye, aapka sawal samajh nahi aaya. Kripya din mein Pakistani khana ya sehat ke bare mein pochhein."'''

    new_code_7 = '''            try:
                response = model.generate_content(
                    f"{system_instruction} User ka sawal: {user_message}"
                )
                
                # Extract the response text
                if response and hasattr(response, 'text'):
                    bot_response = response.text
                elif hasattr(response, '_result') and response._result and hasattr(response._result, 'candidates') and response._result.candidates:
                    # Handle different response structure if needed
                    bot_response = response._result.candidates[0].content.parts[0].text if response._result.candidates[0].content.parts else "Maaf kijiye, aapka sawal samajh nahi aaya. Kripya din mein Pakistani khana ya sehat ke bare mein pochhein."
                else:
                    bot_response = "Maaf kijiye, aapka sawal samajh nahi aaya. Kripya din mein Pakistani khana ya sehat ke bare mein pochhein."
            except Exception as gen_error:
                print(f"Error generating content: {gen_error}")
                bot_response = f"Sorry, I'm having trouble generating a response. Error: {str(gen_error)}"'''

    # Replace the seventh occurrence
    content = content.replace(original_code_7, new_code_7)

    # Write the updated content back to the file
    with open('src/diet_planner/app.py', 'w', encoding='utf-8') as file:
        file.write(content)

    print("File updated successfully!")

if __name__ == "__main__":
    fix_api_calls()