#!/usr/bin/env python3
"""
Enhanced script to remove all subscription-related elements from HTML files
"""

import re

def remove_subscription_content_comprehensive(file_path):
    """Remove all subscription-related content from an HTML file"""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Comprehensive patterns to remove subscription content
    patterns_to_remove = [
        # Subscription plan sections
        r'<!-- All Features Are Now Free! -->.*?</div>\s*</div>\s*</div>',
        r'<div id="premium-features-section"[^>]*>.*?</div>',
        r'<div class="subscription-options">.*?</div>',
        r'<div class="subscription-plan[^>]*>.*?</div>',
        r'<div class="upgrade-section[^>]*>.*?</div>',
        r'<!-- Subscription section removed -->',
        
        # Subscription buttons and elements
        r'<button[^>]*>Subscribe Now</button>',
        r'<button[^>]*>Subscribe Yearly</button>',
        r'<button[^>]*onclick="[^"]*subscribe\([^)]*\)"[^>]*>.*?</button>',
        
        # Subscription text mentions
        r'All Features Are Now Free!',
        r'You have access to all premium features.*?</p>',
        r'Upgrade to Premium.*?</p>',
        r'Free Plan - Limited features available\. Upgrade to Premium.*?</div>',
        r'Unlock Premium.*?Features!',
        r'Save 50% with annual plan!',
        r'premium features',
        r'Upgrade to Premium',
        
        # Price mentions
        r'Rs\.\s*\d+/month',
        r'Rs\.\s*\d+/year',
        
        # Subscription plan titles
        r'<h3>Pro Monthly</h3>',
        r'<h3>Pro Yearly</h3>',
        
        # Subscription-related JavaScript functions
        r'function subscribe\([^)]*\)[^{]*\{[^}]*\}',
        r'onclick="subscribe\([^)]*\)"',
        
        # Subscription status UI elements
        r'<div[^>]*id="current-subscription"[^>]*>.*?</div>',
        r'<div[^>]*class="subscription-status[^>]*>.*?</div>',
        r'<div[^>]*id="premium-features-section"[^>]*>.*?</div>',
        
        # Subscription-related UI sections in diet_plan.html
        r'<div class="form-row"[^>]*id="premiumFeatures"[^>]*>.*?</div>',
        r'Premium Plan Active!.*?</div>',
        
        # Subscription JavaScript calls
        r'loadSubscriptionStatus\(\);',
        r'async function loadSubscriptionStatus\(\)[^{]*\{.*?\}',
        
        # Subscription API calls
        r"fetch\('/api/subscription/status'",
        r"fetch\('/api/subscription/create'",
        
        # Any mentions of subscription tiers
        r'Free Forever',
        r'Free Plan',
        r'Premium Plan',
        
        # All remaining subscription references
        r'All\s+Features\s+Are\s+Now\s+Free!',
        r'Pro\s+Monthly',
        r'Pro\s+Yearly',
    ]
    
    # Apply all patterns to remove subscription content
    for pattern in patterns_to_remove:
        content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Clean up any excess whitespace or malformed HTML that might result
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)  # Replace multiple blank lines with single
    content = re.sub(r'>\s+<', '><', content)  # Remove extra spaces between tags
    content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
    
    # If content was changed, write the new content
    if original_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {file_path} - subscription elements removed")
    else:
        print(f"No subscription elements found in {file_path}")


def main():
    # List of HTML files to process
    html_files = [
        "src/diet_planner/dashboard.html",
        "src/diet_planner/recipes.html", 
        "src/diet_planner/shopping_list.html",
        "src/diet_planner/diet_plan.html",
        "src/diet_planner/settings.html",
        "src/diet_planner/meal_plan.html",
    ]
    
    project_base = "D:/python/Agentic-Ai/Quater4/projects/diet-planner/"
    
    for html_file in html_files:
        file_path = project_base + html_file
        try:
            remove_subscription_content_comprehensive(file_path)
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")


if __name__ == "__main__":
    main()