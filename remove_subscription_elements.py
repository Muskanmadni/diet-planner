#!/usr/bin/env python3
"""
Script to remove subscription-related elements from HTML files
"""

import re

def remove_subscription_content(file_path):
    """Remove subscription-related content from an HTML file"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove the subscription section from dashboard.html
    if "dashboard.html" in file_path:
        # Pattern to match the entire subscription section
        subscription_pattern = r'<!-- All Features Are Now Free! -->\s*<div id="premium-features-section"[^>]*>.*?</div>\s*</div>\s*</div>'
        content = re.sub(subscription_pattern, '', content, flags=re.DOTALL)
    
    # Remove subscription options from recipes.html
    elif "recipes.html" in file_path:
        # Pattern to match subscription options section
        subscription_pattern = r'<p>Upgrade to Premium for.*?</div>\s*</div>\s*</div>'
        content = re.sub(subscription_pattern, '<!-- Subscription section removed -->', content, flags=re.DOTALL)
    
    # Also remove any mention of the subscription text that might be elsewhere
    content = re.sub(r'<h3>Pro Monthly</h3>.*?<button class="btn"[^>]*>Subscribe Now</button>\s*</div>\s*<div class="subscription-plan"[^>]*>.*?<h3>Pro Yearly</h3>.*?<button class="btn"[^>]*>Subscribe Yearly</button>\s*</div>', '', content, flags=re.DOTALL)
    
    # Remove any remaining subscription-related content
    patterns_to_remove = [
        r'All Features Are Now Free!',
        r'You have access to all premium features at no cost.*?</p>',
        r'<p>You have access to all premium features.*?</p>',
        r'<button class="btn"[^>]*>Subscribe Now</button>',
        r'<button class="btn"[^>]*>Subscribe Yearly</button>',
        r'<div class="subscription-options">.*?</div>',
        r'<div class="subscription-plan">.*?</div>',
        r'<div class="subscription-plan"[^>]*>.*?</div>',
        r'<p>Upgrade to Premium for.*?</p>',
        r'Save 50% with annual plan!',
    ]
    
    for pattern in patterns_to_remove:
        content = re.sub(pattern, '', content, flags=re.DOTALL)
    
    # Clean up any extra whitespace or empty divs that might result
    content = re.sub(r'\n\s*\n', '\n', content)  # Remove extra blank lines
    content = re.sub(r'>\s+<', '><', content)    # Remove extra spaces between tags
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Processed {file_path} - subscription elements removed")


def main():
    # List of HTML files to process
    html_files = [
        "src/diet_planner/dashboard.html",
        "src/diet_planner/recipes.html",
        "src/diet_planner/shopping_list.html",  # This might also contain the "All Features Are Now Free" text
    ]
    
    project_base = "D:/python/Agentic-Ai/Quater4/projects/diet-planner/"
    
    for html_file in html_files:
        file_path = project_base + html_file
        try:
            remove_subscription_content(file_path)
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")


if __name__ == "__main__":
    main()