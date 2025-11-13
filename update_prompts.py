import re

# Read the app.py file
with open('D:/python/Agentic-Ai/Quater4/projects/diet-planner/src/diet_planner/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

print("Original file loaded. Length:", len(content))

# Print the exact text around the first prompt to see the exact format
start_idx = content.find('Generate a personalized weekly diet plan for Pakistani cuisine')
if start_idx != -1:
    # Show some context around the match
    context_start = max(0, start_idx - 50)
    context_end = min(len(content), start_idx + 500)
    print("Context around first match:")
    print(repr(content[context_start:context_end]))
    print("="*80)

# Find the first occurrence
pattern1 = '''prompt = f"""Generate a personalized weekly diet plan for Pakistani cuisine based on the following information:
        - Goal: {goal} weight
        - Daily calorie target: {calorie_target} kcal
        - Diet preference: {diet_preference}
        - {medical_info}
        - {allergy_info}

        The diet plan should include:
        1. Breakfast, lunch, dinner, and 2 snacks per day for 7 days
        2. Traditional Pakistani dishes with calorie counts
        3. Protein, carbs, and fat distribution
        4. Hydration recommendations
        5. Cooking tips for healthier preparation

        Format the response in a clear, structured way with days of the week and meals clearly labeled. Use Roman Urdu for explanations where appropriate."""'''

# Count occurrences to make sure we have the right pattern
count1 = content.count(pattern1)
print(f"Pattern 1 found {count1} times")

if count1 > 0:
    # Replace the first occurrence
    new_pattern1 = '''prompt = f"""Generate a personalized weekly diet plan for Pakistani cuisine based on the following information:
        - Goal: {goal} weight
        - Daily calorie target: {calorie_target} kcal
        - Diet preference: {diet_preference}
        - {medical_info}
        - {allergy_info}

        The diet plan should include:
        1. Breakfast, lunch, dinner, and 2 snacks per day for 7 days - each day must have different meals and dishes
        2. Traditional Pakistani dishes with specific calorie counts (no placeholders like "N/A kcal")
        3. Protein, carbs, and fat distribution
        4. Hydration recommendations
        5. Cooking tips for healthier preparation

        CRITICAL REQUIREMENTS:
        - Each day (Monday through Sunday) must have unique and varied meals
        - Do NOT repeat the same dishes across different days
        - Provide specific calorie values for each dish (for example: "280 kcal", "350 kcal" etc., not "N/A kcal")
        - Include different cooking methods and ingredients throughout the week
        - Vary the types of proteins, carbohydrates, and vegetables across days
        - Format the response in a clear, structured way with days of the week and meals clearly labeled. Use Roman Urdu for explanations where appropriate."""'''
    
    new_content = content.replace(pattern1, new_pattern1)
    print(f"After first replacement: {len(new_content)} chars vs {len(content)} original")
    print(f"Count of replacements: {len(new_content) - len(content)}")
    
    # Find the second occurrence in the general endpoint
    pattern2 = '''prompt = f"""Generate a personalized weekly diet plan for Pakistani cuisine based on the following information:
                - Goal: {goal} weight
                - Daily calorie target: {calorie_target} kcal
                - Diet preference: {diet_preference}
                - {medical_info}
                - {allergy_info}

                The diet plan should include:
                1. Breakfast, lunch, dinner, and 2 snacks per day for 7 days
                2. Traditional Pakistani dishes with calorie counts
                3. Protein, carbs, and fat distribution
                4. Hydration recommendations
                5. Cooking tips for healthier preparation

                Format the response in a clear, structured way with days of the week and meals clearly labeled. Use Roman Urdu for explanations where appropriate."""'''
    
    count2 = new_content.count(pattern2)
    print(f"Pattern 2 found {count2} times")
    
    if count2 > 0:
        new_pattern2 = '''prompt = f"""Generate a personalized weekly diet plan for Pakistani cuisine based on the following information:
                - Goal: {goal} weight
                - Daily calorie target: {calorie_target} kcal
                - Diet preference: {diet_preference}
                - {medical_info}
                - {allergy_info}

                The diet plan should include:
                1. Breakfast, lunch, dinner, and 2 snacks per day for 7 days - each day must have different meals and dishes
                2. Traditional Pakistani dishes with specific calorie counts (no placeholders like "N/A kcal")
                3. Protein, carbs, and fat distribution
                4. Hydration recommendations
                5. Cooking tips for healthier preparation

                CRITICAL REQUIREMENTS:
                - Each day (Monday through Sunday) must have unique and varied meals
                - Do NOT repeat the same dishes across different days
                - Provide specific calorie values for each dish (for example: "280 kcal", "350 kcal" etc., not "N/A kcal")
                - Include different cooking methods and ingredients throughout the week
                - Vary the types of proteins, carbohydrates, and vegetables across days
                - Format the response in a clear, structured way with days of the week and meals clearly labeled. Use Roman Urdu for explanations where appropriate."""'''
        
        final_content = new_content.replace(pattern2, new_pattern2)
        print(f"After second replacement: {len(final_content)} chars vs {len(new_content)} after first")
        print(f"Count of second replacements: {len(final_content) - len(new_content)}")
        
        # Write back to file if changes were made
        if len(final_content) != len(content):
            with open('D:/python/Agentic-Ai/Quater4/projects/diet-planner/src/diet_planner/app.py', 'w', encoding='utf-8') as f:
                f.write(final_content)
            print("File updated successfully!")
        else:
            print("No changes were made to the file.")
    else:
        # No second pattern found, write the content with first change only
        if len(new_content) != len(content):
            with open('D:/python/Agentic-Ai/Quater4/projects/diet-planner/src/diet_planner/app.py', 'w', encoding='utf-8') as f:
                f.write(new_content)
            print("File updated with first change only!")
        else:
            print("No changes were made to the file.")
else:
    print("Pattern 1 not found in file!")
    # Let's try finding the text differently
    print("Let's check what's around the expected lines...")