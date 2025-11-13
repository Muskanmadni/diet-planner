import re

def fix_diet_plan_endpoint():
    with open('src/diet_planner/app.py', 'r', encoding='utf-8') as file:
        content = file.read()
    
    # First, let me fix the format_diet_plan_response function
    format_function_old = '''# Helper function to format diet plan response
def format_diet_plan_response(ai_response):
    """
    Takes the AI response and attempts to structure it more consistently
    """
    try:
        # This is a basic formatter - in a real implementation, we might want to use a more
        # sophisticated approach to parse the AI response and structure it consistently
        structured_plan = {
            'full_plan': ai_response,
        }
        return structured_plan
    except Exception:
        # If formatting fails, return the raw response
        return {'full_plan': ai_response}'''
    
    format_function_new = '''# Helper function to format diet plan response
def format_diet_plan_response(ai_response):
    """
    Takes the AI response and attempts to structure it more consistently
    """
    try:
        # Check if the response is HTML (indicates an error page from the API)
        if ai_response and isinstance(ai_response, str) and ai_response.strip().startswith('<'):
            print(f"Warning: AI model returned HTML content instead of text: {ai_response[:100]}...")
            return {
                'full_plan': "Error: The AI service returned an unexpected response. Please try again later.",
                'error': 'AI service returned HTML instead of text'
            }
        
        # This is a basic formatter - in a real implementation, we might want to use a more
        # sophisticated approach to parse the AI response and structure it consistently
        structured_plan = {
            'full_plan': ai_response,
        }
        return structured_plan
    except Exception as e:
        # If formatting fails, return the raw response
        print(f"Error formatting diet plan response: {e}")
        return {'full_plan': ai_response}'''
    
    content = content.replace(format_function_old, format_function_new)
    
    # Now find the problematic area in the diet plan endpoint 
    # Replace the model.generate_content call in the diet plan endpoint with error handling
    diet_plan_old = '''                # Generate diet plan using Gemini
                system_instruction = "You are an expert Pakistani nutritionist. Generate a comprehensive, healthy weekly diet plan with traditional Pakistani foods. Consider dietary restrictions and medical conditions. Respond in a structured format with clear meal plans and nutritional information."

                response = model.generate_content(f"{system_instruction} {prompt}")

                # Extract the response text
                diet_plan_text = response.text if response and hasattr(response, 'text') else "Unable to generate diet plan. Please try again later."'''
    
    diet_plan_new = '''                # Generate diet plan using Gemini
                system_instruction = "You are an expert Pakistani nutritionist. Generate a comprehensive, healthy weekly diet plan with traditional Pakistani foods. Consider dietary restrictions and medical conditions. Respond in a structured format with clear meal plans and nutritional information."

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
                    diet_plan_text = "Error generating diet plan. Please try again later."'''
    
    content = content.replace(diet_plan_old, diet_plan_new)
    
    # Also find the same pattern in the premium diet plan endpoint
    premium_diet_plan_old = '''        # Generate diet plan using Gemini
        system_instruction = "You are an expert Pakistani nutritionist. Generate a comprehensive, healthy weekly diet plan with traditional Pakistani foods. Consider dietary restrictions and medical conditions. Respond in a structured format with clear meal plans and nutritional information."

        response = model.generate_content(f"{system_instruction} {prompt}")

        # Extract the response text and try to parse as JSON
        meal_plan_text = response.text'''
    
    premium_diet_plan_new = '''        # Generate diet plan using Gemini
        system_instruction = "You are an expert Pakistani nutritionist. Generate a comprehensive, healthy weekly diet plan with traditional Pakistani foods. Consider dietary restrictions and medical conditions. Respond in a structured format with clear meal plans and nutritional information."

        try:
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
    
    content = content.replace(premium_diet_plan_old, premium_diet_plan_new)
    
    # Fix the chatbot endpoint too
    chatbot_old = '''            # Generate response using Gemini
            response = model.generate_content(
                f"{system_instruction} User ka sawal: {user_message}"
            )

            # Extract the response text
            bot_response = response.text if response and hasattr(response, 'text') else "Maaf kijiye, aapka sawal samajh nahi aaya. Kripya din mein Pakistani khana ya sehat ke bare mein pochhein."'''
    
    chatbot_new = '''            # Generate response using Gemini
            try:
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
    
    content = content.replace(chatbot_old, chatbot_new)
    
    # Write the updated file
    with open('src/diet_planner/app.py', 'w', encoding='utf-8') as file:
        file.write(content)
    
    print("Fixed the API calls in app.py")

if __name__ == "__main__":
    fix_diet_plan_endpoint()