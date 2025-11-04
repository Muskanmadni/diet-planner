from flask import Flask, request, jsonify, render_template_string, send_from_directory, send_file, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import os
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
from functools import wraps
from flask import redirect, url_for

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nutriguide-prod-secret-key-change-in-production')  # Set a secret key for sessions

# Enable CORS for frontend communication, allowing credentials
CORS(app, supports_credentials=True)

# Database configuration
# For deployment, we'll use DATABASE_URL environment variable if available, otherwise fallback to local SQLite
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # For deployment (e.g., with PostgreSQL)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # For local development with SQLite
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, '..', '..', 'database.db')}"
    
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session['user_id'] is None:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    current_weight = db.Column(db.Float, nullable=True)  # in kg
    height = db.Column(db.Float, nullable=True)  # in cm
    gender = db.Column(db.String(20), nullable=True)
    goal_type = db.Column(db.String(20), nullable=True)  # lose, gain, maintain
    weight_goal = db.Column(db.Float, nullable=True)  # target weight in kg
    bmi = db.Column(db.Float, nullable=True)  # calculated BMI
    daily_calories = db.Column(db.Float, nullable=True)  # calculated daily calories
    subscription_tier = db.Column(db.String(20), nullable=True, default='free')  # free, pro
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    subscription_status = db.Column(db.String(20), nullable=True, default='inactive')  # active, inactive, expired

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'current_weight': self.current_weight,
            'height': self.height,
            'gender': self.gender,
            'goal_type': self.goal_type,
            'weight_goal': self.weight_goal,
            'bmi': self.bmi,
            'daily_calories': self.daily_calories,
            'subscription_tier': self.subscription_tier,
            'subscription_start_date': self.subscription_start_date.isoformat() if self.subscription_start_date else None,
            'subscription_end_date': self.subscription_end_date.isoformat() if self.subscription_end_date else None,
            'subscription_status': self.subscription_status
        }

# Configure Gemini API
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("Warning: GEMINI_API_KEY environment variable not found!")
    model = None
else:
    try:
        print("Gemini API key found, attempting to configure...")
        genai.configure(api_key=api_key)  # Get API key from environment variable
        
        # Test if we can list models
        available_models = []
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            print(f"Available models: {available_models}")
        except Exception as e:
            print(f"Error listing models: {e}")
        
        # Try to create a model with an available version
        try:
            # Use one of the available models from the list
            model = genai.GenerativeModel('gemini-2.5-flash')
            # Test the model with a simple request
            test_response = model.generate_content("Hello")
            print("Gemini model (gemini-2.5-flash) configured successfully")
        except Exception as model_error:
            print(f"Error with gemini-2.5-flash: {model_error}")
            try:
                # Try another available model
                model = genai.GenerativeModel('gemini-2.5-pro')
                test_response = model.generate_content("Hello")
                print("Gemini model (gemini-2.5-pro) configured successfully")
            except Exception as pro_error:
                print(f"Error with gemini-2.5-pro: {pro_error}")
                try:
                    # Try the fallback model
                    model = genai.GenerativeModel('gemini-flash-latest')
                    test_response = model.generate_content("Hello")
                    print("Gemini model (gemini-flash-latest) configured successfully")
                except Exception as latest_error:
                    print(f"Error with all models: {model_error}, {pro_error}, {latest_error}")
                    model = None
                    print("Setting model to None - AI features will not be available")
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")
        model = None

# Create database tables
with app.app_context():
    # Check if we need to recreate the database due to schema changes
    # First, try to create all tables based on models
    db.create_all()
    
    # Print a message to confirm model creation
    print("Database tables created successfully")
    print(f"User model has the following fields: {[column.name for column in User.__table__.columns]}")
    
    # Verify the database exists and is accessible
    try:
        # Test the database connection
        test_user = User.query.first()
        print("Database connection successful. Found existing users:", test_user is not None)
    except Exception as e:
        print(f"Database connection test failed: {e}")
        # If there's a schema mismatch error, we need to recreate the database
        print("Recreating database due to schema mismatch...")
        # Drop and recreate all tables
        db.drop_all()
        db.create_all()
        print("Database recreated successfully")

def calculate_bmi(weight, height):
    """Calculate BMI based on weight (kg) and height (cm)"""
    if not weight or not height or height <= 0:
        return None
    height_m = height / 100  # Convert cm to meters
    bmi = weight / (height_m * height_m)
    return round(bmi, 2)

def calculate_daily_calories(weight, height, gender, goal_type, age=30):  # Default age as placeholder
    """Calculate daily calorie needs based on Mifflin-St Jeor Equation"""
    if not weight or not height or not gender:
        return None
    
    # Mifflin-St Jeor Equation
    if gender.lower() == 'male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    elif gender.lower() == 'female':
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    else:
        # Default to female if gender not specified
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    
    # Activity factor (sedentary lifestyle for default)
    activity_factor = 1.2
    
    # Adjust calories based on goal
    if goal_type == 'lose':
        daily_calories = bmr * activity_factor - 500  # 500 calorie deficit for weight loss
    elif goal_type == 'gain':
        daily_calories = bmr * activity_factor + 500  # 500 calorie surplus for weight gain
    else:
        daily_calories = bmr * activity_factor  # Maintain weight
    
    return round(daily_calories)

# Registration route
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=data['email']).first()
        if existing_user:
            return jsonify({'error': 'User with this email already exists'}), 409
        
        # Calculate BMI and daily calories
        weight = data.get('current_weight')
        height = data.get('height')
        gender = data.get('gender')
        goal_type = data.get('goal_type')
        
        bmi = calculate_bmi(weight, height)
        daily_calories = calculate_daily_calories(weight, height, gender, goal_type)
        
        # Create new user with all fields
        user = User(
            email=data['email'],
            current_weight=weight,
            height=height,
            gender=gender,
            goal_type=goal_type,
            weight_goal=data.get('weight_goal'),
            bmi=bmi,
            daily_calories=daily_calories
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'message': 'User registered successfully',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Local food database (placeholder)
LOCAL_FOOD_DATABASE = {
    'roti': {
        'name': 'Roti',
        'calories': 70,  # per piece
        'carbs': 15,     # in grams
        'protein': 3,    # in grams
        'fat': 0.5       # in grams
    },
    'biryani': {
        'name': 'Biryani',
        'calories': 250, # per cup
        'carbs': 35,     # in grams
        'protein': 8,    # in grams
        'fat': 10        # in grams
    },
    'daal': {
        'name': 'Daal (Lentils)',
        'calories': 120, # per cup
        'carbs': 20,     # in grams
        'protein': 9,    # in grams
        'fat': 2         # in grams
    },
    'rice': {
        'name': 'Rice',
        'calories': 200, # per cup
        'carbs': 45,     # in grams
        'protein': 4,    # in grams
        'fat': 0.5       # in grams
    },
    'chicken': {
        'name': 'Chicken',
        'calories': 165, # per 100g
        'carbs': 0,      # in grams
        'protein': 31,   # in grams
        'fat': 3.6      # in grams
    },
    'kheer': {
        'name': 'Kheer',
        'calories': 150, # per cup
        'carbs': 28,     # in grams
        'protein': 4,    # in grams
        'fat': 2         # in grams
    },
    'egg': {
        'name': 'Egg',
        'calories': 70,  # per egg
        'carbs': 0.6,    # in grams
        'protein': 6,    # in grams
        'fat': 5         # in grams
    },
    'aloo': {
        'name': 'Aloo (Potato)',
        'calories': 77,  # per 100g
        'carbs': 17,     # in grams
        'protein': 2,    # in grams
        'fat': 0.1       # in grams
    },
    'gobi': {
        'name': 'Gobi (Cauliflower)',
        'calories': 25,  # per 100g
        'carbs': 5,      # in grams
        'protein': 2,    # in grams
        'fat': 0.3       # in grams
    },
    'mix_vegetable': {
        'name': 'Mixed Vegetables',
        'calories': 45,  # per 100g
        'carbs': 8,      # in grams
        'protein': 2,    # in grams
        'fat': 0.4       # in grams
    },
    'paratha': {
        'name': 'Paratha',
        'calories': 150, # per piece
        'carbs': 20,     # in grams
        'protein': 4,    # in grams
        'fat': 6         # in grams
    }
}

# Limited food recommendations for free users
LIMITED_FOOD_RECOMMENDATIONS = {
    'breakfast': [
        {'name': 'Roti with Daal', 'calories': 190},
        {'name': 'Paratha with Curd', 'calories': 250},
        {'name': 'Omelette with Bread', 'calories': 200},
        {'name': 'Poha', 'calories': 180},
        {'name': 'Upma', 'calories': 220}
    ],
    'lunch': [
        {'name': 'Rice with Daal and Vegetable', 'calories': 350},
        {'name': 'Roti with Chicken Curry', 'calories': 400},
        {'name': 'Biryani (small portion)', 'calories': 350},
        {'name': 'Dal Rice with Salad', 'calories': 300},
        {'name': 'Vegetable Curry with Roti', 'calories': 320}
    ],
    'dinner': [
        {'name': 'Roti with Daal and Sabzi', 'calories': 300},
        {'name': 'Chicken with Rice', 'calories': 350},
        {'name': 'Vegetable Curry with Roti', 'calories': 280},
        {'name': 'Daal with Rice', 'calories': 280},
        {'name': 'Simple Khichdi', 'calories': 250}
    ],
    'snack': [
        {'name': 'Fruit Salad', 'calories': 100},
        {'name': 'Tea with Biscuits', 'calories': 150},
        {'name': 'Boiled Egg', 'calories': 70},
        {'name': 'Nuts (small portion)', 'calories': 180},
        {'name': 'Yogurt', 'calories': 120}
    ]
}

# Motivational tips for free users
MOTIVATIONAL_TIPS = [
    "Start your day with a glass of water to boost metabolism!",
    "Include at least 5 servings of fruits and vegetables in your diet daily.",
    "Choose whole grains over refined grains for better nutrition.",
    "Stay hydrated - drink at least 8 glasses of water daily.",
    "Plan your meals to avoid unhealthy food choices.",
    "Start with small steps - every healthy choice matters!",
    "Try to eat 2 pieces of fruit as snacks instead of processed food.",
    "Take a 10-minute walk after meals for better digestion.",
    "Cook at home to control ingredients and portions.",
    "Listen to your body - eat when hungry, stop when full."
]

# Free user custom meals limit
FREE_USER_MEAL_LIMIT = 5

@app.route('/api/food_search', methods=['GET'])
def food_search():
    try:
        food_name = request.args.get('food_name', '').lower().strip()
        
        if not food_name:
            return jsonify({'error': 'Food name parameter is required'}), 400
        
        # Search for the food in the local database
        result = []
        for key, value in LOCAL_FOOD_DATABASE.items():
            if food_name in key or food_name in value['name'].lower():
                result.append(value)
        
        if not result:
            return jsonify({'message': f'No food items found matching "{food_name}"'}), 404
        
        return jsonify({
            'results': result,
            'count': len(result)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    try:
        data = request.get_json()
        user_message = data.get('user_message', '').strip()
        
        if not user_message:
            return jsonify({'error': 'User message is required'}), 400
        
        # Check for expert hand-off trigger
        if 'Mujhe expert se baat karni hai' in user_message:
            return jsonify({
                'response': 'Aap ke sawal ka jawab dena zaroori hai. Kripya apna contact number ya email provide karein taake hum aap se expert ke through rabta kar sakein.',
                'needs_expert': True
            }), 200
        
        # Check if model is available
        if model is None:
            return jsonify({
                'response': 'Sorry, the AI model is not available. Please contact the administrator.',
                'needs_expert': False
            }), 500
        
        # System instructions for Pakistani diet and health matters in Roman Urdu
        system_instruction = "Aap Pakistani diet aur health matters par baat karne wale nutritionist hain. Jawab Roman Urdu mein dena. Sirf Pakistani diet, traditional foods, aur health concerns par bat karna. Koi bhi non-Pakistani diet ya western foods ke baare mein bat karne se mana karna. jawab chota hoga, seedha aur asan alfaaz mein jawab dein."
        
        # Generate response using Gemini
        try:
            response = model.generate_content(
                f"{system_instruction} User ka sawal: {user_message}"
            )
            
            # Extract the response text
            bot_response = response.text if response and hasattr(response, 'text') else "Maaf kijiye, aapka sawal samajh nahi aaya. Kripya din mein Pakistani khana ya sehat ke bare mein pochhein."
        except Exception as gen_error:
            print(f"Error generating content: {gen_error}")
            bot_response = f"Sorry, I'm having trouble generating a response. Error: {str(gen_error)}"
        
        return jsonify({
            'response': bot_response,
            'needs_expert': False
        }), 200
        
    except Exception as e:
        print(f"Error in chatbot endpoint: {e}")
        return jsonify({'error': str(e)}), 500

# Default route to serve the landing page (public)
@app.route('/')
def landing_page():
    # Check if user is already logged in
    user_id = session.get('user_id')
    if user_id:
        # If user is logged in, redirect to dashboard
        return redirect(url_for('dashboard'))
    else:
        # If user is not logged in, show landing page
        html_path = os.path.join(os.path.dirname(__file__), 'landing.html')
        return send_file(html_path)

# Route to serve dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
    return send_file(html_path)

# Route to serve chatbot interface
@app.route('/chatbot')
@login_required
def chatbot_ui():
    html_path = os.path.join(os.path.dirname(__file__), 'chatbot.html')
    return send_file(html_path)

# Route to serve register page
@app.route('/register')
def register_page():
    html_path = os.path.join(os.path.dirname(__file__), 'register.html')
    return send_file(html_path)

# Route to serve login page
@app.route('/login')
def login_page():
    html_path = os.path.join(os.path.dirname(__file__), 'login.html')
    return send_file(html_path)

# Route to serve diet plan page
@app.route('/diet-plan')
@login_required
def diet_plan():
    html_path = os.path.join(os.path.dirname(__file__), 'diet_plan.html')
    return send_file(html_path)

# Route to serve recipes page
@app.route('/recipes')
@login_required
def recipes():
    html_path = os.path.join(os.path.dirname(__file__), 'recipes.html')
    return send_file(html_path)

# Route to serve shopping list page
@app.route('/shopping-list')
@login_required
def shopping_list():
    html_path = os.path.join(os.path.dirname(__file__), 'shopping_list.html')
    return send_file(html_path)

# Route to serve static files (HTML files) - excluding the root index
@app.route('/<path:filename>')
def serve_static_html(filename):
    if filename.endswith('.html'):
        file_path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(file_path):
            return send_file(file_path)
        else:
            return jsonify({'error': 'File not found'}), 404
    else:
        # For non-HTML files or specific routes, return error
        return jsonify({'error': 'File not found'}), 404

# Login route
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find user by email
        user = User.query.filter_by(email=data['email']).first()
        if not user or not user.check_password(data['password']):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Store user ID in session
        session['user_id'] = user.id
        
        # Return user info (in a real app, you'd generate a JWT token)
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Logout route
@app.route('/api/logout', methods=['POST'])
def logout():
    try:
        # Clear the user session
        session.pop('user_id', None)
        
        return jsonify({
            'message': 'Logout successful'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Get current user info
@app.route('/api/current_user', methods=['GET'])
def current_user():
    try:
        # Check if user is logged in by checking session
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        # Get user from database using session ID
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'message': 'User info retrieved successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Subscription plans
SUBSCRIPTION_PLANS = {
    'pro_monthly': {
        'name': 'Pro Monthly',
        'price': 500,  # 500 PKR
        'duration': 30,  # days
        'features': [
            'Personalised Weekly Meal Plan Generator',
            'Automatic Macro Distribution',
            'Unlimited Custom Meals & Recipes',
            'Smart Recipe Suggestions',
            'Shopping List Generator',
            'Meal Swap Option'
        ]
    },
    'pro_yearly': {
        'name': 'Pro Yearly',
        'price': 1500,  # 1500 PKR
        'duration': 365,  # days
        'features': [
            'Personalised Weekly Meal Plan Generator',
            'Automatic Macro Distribution',
            'Unlimited Custom Meals & Recipes',
            'Smart Recipe Suggestions',
            'Shopping List Generator',
            'Meal Swap Option'
        ]
    }
}

# Get subscription plans
@app.route('/api/subscription/plans', methods=['GET'])
def get_subscription_plans():
    try:
        return jsonify({
            'plans': SUBSCRIPTION_PLANS
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Create subscription
@app.route('/api/subscription/create', methods=['POST'])
def create_subscription():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        plan_id = data.get('plan_id')
        
        if not plan_id or plan_id not in SUBSCRIPTION_PLANS:
            return jsonify({'error': 'Invalid plan ID'}), 400
        
        plan = SUBSCRIPTION_PLANS[plan_id]
        
        # Calculate subscription dates
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=plan['duration'])
        
        # Update user subscription
        user.subscription_tier = 'pro'
        user.subscription_start_date = start_date
        user.subscription_end_date = end_date
        user.subscription_status = 'active'
        
        db.session.commit()
        
        return jsonify({
            'message': 'Subscription created successfully',
            'plan': plan,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Get user subscription status
@app.route('/api/subscription/status', methods=['GET'])
def get_subscription_status():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if subscription is expired
        if user.subscription_end_date and datetime.utcnow() > user.subscription_end_date:
            user.subscription_status = 'expired'
            db.session.commit()
        
        return jsonify({
            'subscription_tier': user.subscription_tier,
            'subscription_start_date': user.subscription_start_date.isoformat() if user.subscription_start_date else None,
            'subscription_end_date': user.subscription_end_date.isoformat() if user.subscription_end_date else None,
            'subscription_status': user.subscription_status
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Cancel subscription
@app.route('/api/subscription/cancel', methods=['POST'])
def cancel_subscription():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Set subscription to inactive but keep historical data
        user.subscription_status = 'inactive'
        
        db.session.commit()
        
        return jsonify({
            'message': 'Subscription cancelled successfully'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Helper function to check if user has premium access
def require_premium(func):
    """Decorator to check if user has premium subscription"""
    def wrapper(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.subscription_status != 'active':
            return jsonify({'error': 'Premium subscription required for this feature'}), 402
        
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# Weekly Meal Plan Generator
@app.route('/api/premium/meal-plan', methods=['POST'])
@require_premium
def generate_weekly_meal_plan():
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        data = request.get_json()
        goal = data.get('goal', user.goal_type) or 'maintain'
        calorie_target = data.get('calorie_target', user.daily_calories) or 2000
        non_veg_preference = data.get('non_veg_preference', False)
        
        # Check if model is available
        if model is None:
            return jsonify({
                'error': 'AI model not available'
            }), 500
        
        # Create prompt for AI to generate weekly meal plan
        food_preference = "non-vegetarian" if non_veg_preference else "vegetarian"
        prompt = f"""Generate a personalized weekly meal plan for a {food_preference} Pakistani diet with {calorie_target} daily calories for weight {goal} goal. 
        Include 2 main meals per day (breakfast and dinner) for 7 days. 
        Recommend traditional Pakistani dishes with their calorie counts. 
        Format the response in JSON with days of the week as keys and meals as values."""
        
        # Generate meal plan using Gemini
        system_instruction = "You are a Pakistani nutritionist. Recommend traditional Pakistani food items with approximate calorie counts. Respond in JSON format with days as keys and meal objects containing breakfast and dinner."
        
        response = model.generate_content(f"{system_instruction} {prompt}")
        
        # Extract the response text and try to parse as JSON
        meal_plan_text = response.text
        # Simple approach - return the generated text as part of response
        # In a real implementation, we'd need to parse the AI response better
        
        return jsonify({
            'meal_plan': meal_plan_text,
            'goal': goal,
            'calorie_target': calorie_target,
            'non_veg_preference': non_veg_preference
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Macro Distribution Tracker
@app.route('/api/premium/macro-tracker', methods=['POST'])
@require_premium
def calculate_macro_distribution():
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        data = request.get_json()
        calorie_target = data.get('calorie_target', user.daily_calories) or 2000
        
        # Calculate macro distribution based on calorie target
        # Standard distribution: 40% carbs, 30% protein, 30% fat
        carbs_calories = int(calorie_target * 0.4)
        protein_calories = int(calorie_target * 0.3)
        fat_calories = int(calorie_target * 0.3)
        
        carbs_grams = int(carbs_calories / 4)  # 4 calories per gram of carbs
        protein_grams = int(protein_calories / 4)  # 4 calories per gram of protein
        fat_grams = int(fat_calories / 9)  # 9 calories per gram of fat
        
        return jsonify({
            'calorie_target': calorie_target,
            'macros': {
                'carbohydrates': {
                    'grams': carbs_grams,
                    'calories': carbs_calories
                },
                'protein': {
                    'grams': protein_grams,
                    'calories': protein_calories
                },
                'fat': {
                    'grams': fat_grams,
                    'calories': fat_calories
                }
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Custom Meals & Recipes Management
class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float)  # in grams
    carbs = db.Column(db.Float)    # in grams
    fat = db.Column(db.Float)      # in grams
    is_vegetarian = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'calories': self.calories,
            'protein': self.protein,
            'carbs': self.carbs,
            'fat': self.fat,
            'is_vegetarian': self.is_vegetarian,
            'created_at': self.created_at.isoformat()
        }

# Add meal to user's collection
@app.route('/api/premium/meals', methods=['POST'])
@require_premium
def add_meal():
    try:
        user_id = session.get('user_id')
        
        data = request.get_json()
        meal = Meal(
            user_id=user_id,
            name=data['name'],
            description=data.get('description', ''),
            calories=data['calories'],
            protein=data.get('protein', 0),
            carbs=data.get('carbs', 0),
            fat=data.get('fat', 0),
            is_vegetarian=data.get('is_vegetarian', True)
        )
        
        db.session.add(meal)
        db.session.commit()
        
        return jsonify({
            'message': 'Meal added successfully',
            'meal': meal.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Get user's custom meals
@app.route('/api/premium/meals', methods=['GET'])
@require_premium
def get_meals():
    try:
        user_id = session.get('user_id')
        
        meals = Meal.query.filter_by(user_id=user_id).all()
        meals_list = [meal.to_dict() for meal in meals]
        
        return jsonify({
            'meals': meals_list,
            'count': len(meals_list)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Smart Recipe Suggestions
@app.route('/api/premium/recipe-suggestions', methods=['POST'])
@require_premium
def get_recipe_suggestions():
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        data = request.get_json()
        ingredients = data.get('ingredients', [])
        
        if not ingredients:
            return jsonify({'error': 'Ingredients list is required'}), 400
        
        # Check if model is available
        if model is None:
            return jsonify({
                'error': 'AI model not available'
            }), 500
        
        ingredients_str = ', '.join(ingredients)
        prompt = f"""Suggest Pakistani recipes using these ingredients: {ingredients_str}. 
        Include calorie information and nutritional values. 
        Prioritize recipes that match the user's dietary goals for weight {user.goal_type}."""
        
        system_instruction = "You are a Pakistani nutritionist. Recommend traditional Pakistani recipes using the provided ingredients. Include approximate calorie counts and nutritional values."
        
        response = model.generate_content(f"{system_instruction} {prompt}")
        
        return jsonify({
            'suggestions': response.text,
            'ingredients': ingredients
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Shopping List Generator
@app.route('/api/premium/shopping-list', methods=['POST'])
@require_premium
def generate_shopping_list():
    try:
        user_id = session.get('user_id')
        
        data = request.get_json()
        meal_plan = data.get('meal_plan', [])
        
        if not meal_plan:
            return jsonify({'error': 'Meal plan is required'}), 400
        
        # Check if model is available
        if model is None:
            return jsonify({
                'error': 'AI model not available'
            }), 500
        
        meal_plan_str = json.dumps(meal_plan)
        prompt = f"""Generate a shopping list from this meal plan: {meal_plan_str}. 
        List all the ingredients needed with approximate quantities for Pakistani cooking."""
        
        system_instruction = "You are a Pakistani cooking assistant. Generate a shopping list from the provided meal plan with traditional Pakistani ingredients and their quantities."
        
        response = model.generate_content(f"{system_instruction} {prompt}")
        
        return jsonify({
            'shopping_list': response.text,
            'meal_plan_items': len(meal_plan)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Helper function to format diet plan response
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
        return {'full_plan': ai_response}

# AI-Powered Diet Plan Generator
@app.route('/api/premium/diet-plan', methods=['POST'])
@require_premium
def generate_diet_plan():
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        
        data = request.get_json()
        
        # Get user data with fallbacks
        goal = data.get('goal') or (user.goal_type if user else 'maintain') or 'maintain'
        calorie_target = data.get('calorie_target') or (user.daily_calories if user else 2000) or 2000
        diet_preference = data.get('diet_preference', 'balanced')  # balanced, low-carb, high-protein, etc.
        allergies = data.get('allergies', [])
        medical_conditions = data.get('medical_conditions', [])
        
        # Check if model is available
        if model is None:
            # If AI model is not available, fall back to basic plan generation
            # This uses the same logic as the free diet plan generator but with premium user access
            import random
            
            # Generate a basic diet plan using the local food database
            breakfast_options = LIMITED_FOOD_RECOMMENDATIONS['breakfast']
            lunch_options = LIMITED_FOOD_RECOMMENDATIONS['lunch']
            dinner_options = LIMITED_FOOD_RECOMMENDATIONS['dinner']
            snack_options = LIMITED_FOOD_RECOMMENDATIONS['snack']
            
            # Create a simple 7-day diet plan
            diet_plan = {}
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            for day in days:
                diet_plan[day] = {
                    'breakfast': random.choice(breakfast_options),
                    'lunch': random.choice(lunch_options),
                    'dinner': random.choice(dinner_options),
                    'snacks': [random.choice(snack_options), random.choice(snack_options)]
                }
            
            # Calculate total calories for the plan
            total_daily_calories = 0
            for day in diet_plan.values():
                total_daily_calories += day['breakfast']['calories']
                total_daily_calories += day['lunch']['calories']
                total_daily_calories += day['dinner']['calories']
                total_daily_calories += sum(snack['calories'] for snack in day['snacks'])
            
            avg_daily_calories = total_daily_calories / 7
            
            # Create a text-based diet plan representation
            plan_text = f"Pakistani Weekly Diet Plan for {goal} weight with {diet_preference} preference\n"
            plan_text += f"Daily Calorie Target: {calorie_target} kcal\n"
            if allergies:
                plan_text += f"Allergies to avoid: {', '.join(allergies)}\n"
            if medical_conditions:
                plan_text += f"Medical conditions to consider: {', '.join(medical_conditions)}\n"
            plan_text += "\nWeekly Plan:\n"
            
            for day, meals in diet_plan.items():
                plan_text += f"\n{day}:\n"
                plan_text += f"  Breakfast: {meals['breakfast']['name']} ({meals['breakfast']['calories']} kcal)\n"
                plan_text += f"  Lunch: {meals['lunch']['name']} ({meals['lunch']['calories']} kcal)\n"
                plan_text += f"  Dinner: {meals['dinner']['name']} ({meals['dinner']['calories']} kcal)\n"
                plan_text += f"  Snacks: {meals['snacks'][0]['name']} ({meals['snacks'][0]['calories']} kcal), {meals['snacks'][1]['name']} ({meals['snacks'][1]['calories']} kcal)\n"
            
            plan_text += f"\nNote: This is a basic plan generated without AI. Please consult with a nutritionist for specific dietary needs."
            
            return jsonify({
                'diet_plan': {'full_plan': plan_text},
                'original_response': plan_text,
                'goal': goal,
                'calorie_target': calorie_target,
                'diet_preference': diet_preference,
                'allergies': allergies,
                'medical_conditions': medical_conditions,
                'plan_type': 'basic_fallback_plan'
            }), 200
        
        # Create prompt for AI to generate personalized diet plan (original AI logic)
        medical_info = f"Medical conditions: {', '.join(medical_conditions)}" if medical_conditions else "No medical conditions"
        allergy_info = f"Allergies: {', '.join(allergies)}" if allergies else "No known allergies"
        
        prompt = f"""Generate a personalized weekly diet plan for Pakistani cuisine based on the following information:
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
        
        Format the response in a clear, structured way with days of the week and meals clearly labeled. Use Roman Urdu for explanations where appropriate."""
        
        # Generate diet plan using Gemini
        system_instruction = "You are an expert Pakistani nutritionist. Generate a comprehensive, healthy weekly diet plan with traditional Pakistani foods. Consider dietary restrictions and medical conditions. Respond in a structured format with clear meal plans and nutritional information."
        
        response = model.generate_content(f"{system_instruction} {prompt}")
        
        # Extract the response text
        diet_plan_text = response.text if response and hasattr(response, 'text') else "Unable to generate diet plan. Please try again later."
        
        # Format the response
        formatted_plan = format_diet_plan_response(diet_plan_text)
        
        return jsonify({
            'diet_plan': formatted_plan,
            'original_response': diet_plan_text,  # Keep original for reference
            'goal': goal,
            'calorie_target': calorie_target,
            'diet_preference': diet_preference,
            'allergies': allergies,
            'medical_conditions': medical_conditions
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Free user custom meals
class FreeMeal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    calories = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'calories': self.calories,
            'created_at': self.created_at.isoformat()
        }

# Meal log model for tracking daily meals
class MealLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    meal_name = db.Column(db.String(100), nullable=False)
    calories = db.Column(db.Float, nullable=False)
    meal_time = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner, snack
    log_date = db.Column(db.Date, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'meal_name': self.meal_name,
            'calories': self.calories,
            'meal_time': self.meal_time,
            'log_date': self.log_date.isoformat(),
            'created_at': self.created_at.isoformat()
        }

# Free tier - Basic Calorie Tracker
@app.route('/api/free/log_meal', methods=['POST'])
def log_meal():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        # Validate required fields
        if not data.get('meal_name') or not data.get('calories'):
            return jsonify({'error': 'Meal name and calories are required'}), 400
        
        # Check if food exists in database
        meal_name = data['meal_name'].lower()
        food_item = None
        
        for key, value in LOCAL_FOOD_DATABASE.items():
            if meal_name in key or meal_name in value['name'].lower():
                food_item = value
                break
        
        # If not in DB, use provided calories
        calories = float(data['calories'])
        if food_item:
            calories = food_item['calories']
        
        # Log the meal
        meal_log = MealLog(
            user_id=user_id,
            meal_name=data['meal_name'],
            calories=calories,
            meal_time=data.get('meal_time', 'snack'),  # default to snack
            log_date=datetime.utcnow().date()
        )
        
        db.session.add(meal_log)
        db.session.commit()
        
        return jsonify({
            'message': 'Meal logged successfully',
            'meal_log': meal_log.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Get logged meals for today
@app.route('/api/free/today_meals', methods=['GET'])
def get_today_meals():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        today = datetime.utcnow().date()
        
        meals = MealLog.query.filter_by(user_id=user_id, log_date=today).all()
        meals_list = [meal.to_dict() for meal in meals]
        
        # Calculate total calories
        total_calories = sum(meal['calories'] for meal in meals_list)
        
        return jsonify({
            'meals': meals_list,
            'total_calories': total_calories,
            'date': today.isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Get limited recommendations for free users
@app.route('/api/free/recommendations', methods=['GET'])
def get_food_recommendations():
    try:
        meal_type = request.args.get('type', 'breakfast')
        
        if meal_type not in LIMITED_FOOD_RECOMMENDATIONS:
            meal_type = 'breakfast'
        
        recommendations = LIMITED_FOOD_RECOMMENDATIONS[meal_type]
        
        return jsonify({
            'meal_type': meal_type,
            'recommendations': recommendations
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# General diet plan generator that works for all users (with fallback logic)
@app.route('/api/diet-plan', methods=['POST'])
def generate_diet_plan_general():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        goal = data.get('goal') or (user.goal_type if user else 'maintain') or 'maintain'
        calorie_target = data.get('calorie_target') or (user.daily_calories if user else 2000) or 2000
        diet_preference = data.get('diet_preference', 'balanced')  # balanced, low-carb, high-protein, etc.
        allergies = data.get('allergies', [])
        medical_conditions = data.get('medical_conditions', [])
        
        # Check if user has premium subscription
        has_premium = (user.subscription_status == 'active')
        
        if has_premium:
            # Premium user - attempt to use AI if available
            if model is not None:
                # Use AI model for premium users
                # Create prompt for AI to generate personalized diet plan
                medical_info = f"Medical conditions: {', '.join(medical_conditions)}" if medical_conditions else "No medical conditions"
                allergy_info = f"Allergies: {', '.join(allergies)}" if allergies else "No known allergies"
                
                prompt = f"""Generate a personalized weekly diet plan for Pakistani cuisine based on the following information:
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
                
                Format the response in a clear, structured way with days of the week and meals clearly labeled. Use Roman Urdu for explanations where appropriate."""
                
                # Generate diet plan using Gemini
                system_instruction = "You are an expert Pakistani nutritionist. Generate a comprehensive, healthy weekly diet plan with traditional Pakistani foods. Consider dietary restrictions and medical conditions. Respond in a structured format with clear meal plans and nutritional information."
                
                response = model.generate_content(f"{system_instruction} {prompt}")
                
                # Extract the response text
                diet_plan_text = response.text if response and hasattr(response, 'text') else "Unable to generate diet plan. Please try again later."
                
                # Format the response
                formatted_plan = format_diet_plan_response(diet_plan_text)
                
                return jsonify({
                    'diet_plan': formatted_plan,
                    'original_response': diet_plan_text,
                    'goal': goal,
                    'calorie_target': calorie_target,
                    'diet_preference': diet_preference,
                    'allergies': allergies,
                    'medical_conditions': medical_conditions,
                    'plan_type': 'ai_generated_premium'
                }), 200
            else:
                # Premium user but no AI available - use fallback
                import random
                
                # Generate a basic diet plan using the local food database
                breakfast_options = LIMITED_FOOD_RECOMMENDATIONS['breakfast']
                lunch_options = LIMITED_FOOD_RECOMMENDATIONS['lunch']
                dinner_options = LIMITED_FOOD_RECOMMENDATIONS['dinner']
                snack_options = LIMITED_FOOD_RECOMMENDATIONS['snack']
                
                # Create a simple 7-day diet plan
                diet_plan = {}
                days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                
                for day in days:
                    diet_plan[day] = {
                        'breakfast': random.choice(breakfast_options),
                        'lunch': random.choice(lunch_options),
                        'dinner': random.choice(dinner_options),
                        'snacks': [random.choice(snack_options), random.choice(snack_options)]
                    }
                
                # Calculate total calories for the plan
                total_daily_calories = 0
                for day in diet_plan.values():
                    total_daily_calories += day['breakfast']['calories']
                    total_daily_calories += day['lunch']['calories']
                    total_daily_calories += day['dinner']['calories']
                    total_daily_calories += sum(snack['calories'] for snack in day['snacks'])
                
                avg_daily_calories = total_daily_calories / 7
                
                # Create a text-based diet plan representation
                plan_text = f"Pakistani Weekly Diet Plan for {goal} weight with {diet_preference} preference\n"
                plan_text += f"Daily Calorie Target: {calorie_target} kcal\n"
                if allergies:
                    plan_text += f"Allergies to avoid: {', '.join(allergies)}\n"
                if medical_conditions:
                    plan_text += f"Medical conditions to consider: {', '.join(medical_conditions)}\n"
                plan_text += "\nWeekly Plan:\n"
                
                for day, meals in diet_plan.items():
                    plan_text += f"\n{day}:\n"
                    plan_text += f"  Breakfast: {meals['breakfast']['name']} ({meals['breakfast']['calories']} kcal)\n"
                    plan_text += f"  Lunch: {meals['lunch']['name']} ({meals['lunch']['calories']} kcal)\n"
                    plan_text += f"  Dinner: {meals['dinner']['name']} ({meals['dinner']['calories']} kcal)\n"
                    plan_text += f"  Snacks: {meals['snacks'][0]['name']} ({meals['snacks'][0]['calories']} kcal), {meals['snacks'][1]['name']} ({meals['snacks'][1]['calories']} kcal)\n"
                
                plan_text += f"\nNote: This is a plan generated without AI. Please consult with a nutritionist for specific dietary needs."
                
                return jsonify({
                    'diet_plan': {'full_plan': plan_text},
                    'original_response': plan_text,
                    'goal': goal,
                    'calorie_target': calorie_target,
                    'diet_preference': diet_preference,
                    'allergies': allergies,
                    'medical_conditions': medical_conditions,
                    'plan_type': 'basic_fallback_premium'
                }), 200
        else:
            # Free user - use basic generator
            import random
            
            # Generate a basic diet plan using the local food database
            breakfast_options = LIMITED_FOOD_RECOMMENDATIONS['breakfast']
            lunch_options = LIMITED_FOOD_RECOMMENDATIONS['lunch']
            dinner_options = LIMITED_FOOD_RECOMMENDATIONS['dinner']
            snack_options = LIMITED_FOOD_RECOMMENDATIONS['snack']
            
            # Create a simple 7-day diet plan
            diet_plan = {}
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            for day in days:
                diet_plan[day] = {
                    'breakfast': random.choice(breakfast_options),
                    'lunch': random.choice(lunch_options),
                    'dinner': random.choice(dinner_options),
                    'snacks': [random.choice(snack_options), random.choice(snack_options)]
                }
            
            # Calculate total calories for the plan
            total_daily_calories = 0
            for day in diet_plan.values():
                total_daily_calories += day['breakfast']['calories']
                total_daily_calories += day['lunch']['calories']
                total_daily_calories += day['dinner']['calories']
                total_daily_calories += sum(snack['calories'] for snack in day['snacks'])
            
            avg_daily_calories = total_daily_calories / 7
            
            return jsonify({
                'diet_plan': diet_plan,
                'goal': goal,
                'calorie_target': calorie_target,
                'avg_daily_calories': round(avg_daily_calories, 2),
                'plan_type': 'basic_free_plan',
                'tip': random.choice(MOTIVATIONAL_TIPS)
            }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Free diet plan generator for non-premium users
@app.route('/api/free/diet-plan', methods=['POST'])
def generate_free_diet_plan():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        goal = data.get('goal') or (user.goal_type if user else 'maintain') or 'maintain'
        calorie_target = data.get('calorie_target') or (user.daily_calories if user else 2000) or 2000
        
        # Generate a basic diet plan using the local food database
        breakfast_options = LIMITED_FOOD_RECOMMENDATIONS['breakfast']
        lunch_options = LIMITED_FOOD_RECOMMENDATIONS['lunch']
        dinner_options = LIMITED_FOOD_RECOMMENDATIONS['dinner']
        snack_options = LIMITED_FOOD_RECOMMENDATIONS['snack']
        
        import random
        
        # Create a simple 7-day diet plan
        diet_plan = {}
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        for day in days:
            diet_plan[day] = {
                'breakfast': random.choice(breakfast_options),
                'lunch': random.choice(lunch_options),
                'dinner': random.choice(dinner_options),
                'snacks': [random.choice(snack_options), random.choice(snack_options)]
            }
        
        # Calculate total calories for the plan
        total_daily_calories = 0
        for day in diet_plan.values():
            total_daily_calories += day['breakfast']['calories']
            total_daily_calories += day['lunch']['calories']
            total_daily_calories += day['dinner']['calories']
            total_daily_calories += sum(snack['calories'] for snack in day['snacks'])
        
        avg_daily_calories = total_daily_calories / 7
        
        return jsonify({
            'diet_plan': diet_plan,
            'goal': goal,
            'calorie_target': calorie_target,
            'avg_daily_calories': round(avg_daily_calories, 2),
            'plan_type': 'basic_free_plan',
            'tip': random.choice(MOTIVATIONAL_TIPS)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Save custom meal for free users (limited to 5)
@app.route('/api/free/custom_meal', methods=['POST'])
def save_custom_meal():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if user is on free tier and has reached limit
        if user.subscription_status == 'inactive' or user.subscription_tier == 'free' or user.subscription_status is None:
            existing_meals_count = FreeMeal.query.filter_by(user_id=user_id).count()
            if existing_meals_count >= FREE_USER_MEAL_LIMIT:
                return jsonify({'error': f'Free users can only save up to {FREE_USER_MEAL_LIMIT} custom meals'}), 400
        
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('calories'):
            return jsonify({'error': 'Meal name and calories are required'}), 400
        
        custom_meal = FreeMeal(
            user_id=user_id,
            name=data['name'],
            description=data.get('description', ''),
            calories=float(data['calories'])
        )
        
        db.session.add(custom_meal)
        db.session.commit()
        
        return jsonify({
            'message': 'Custom meal saved successfully',
            'meal': custom_meal.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Get user's custom meals
@app.route('/api/free/custom_meals', methods=['GET'])
def get_custom_meals():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        meals = FreeMeal.query.filter_by(user_id=user_id).all()
        meals_list = [meal.to_dict() for meal in meals]
        
        return jsonify({
            'meals': meals_list,
            'count': len(meals_list),
            'limit': FREE_USER_MEAL_LIMIT
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Get motivational tips
@app.route('/api/free/tips', methods=['GET'])
def get_motivational_tips():
    try:
        import random
        tip = random.choice(MOTIVATIONAL_TIPS)
        
        return jsonify({
            'tip': tip
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Get daily summary
@app.route('/api/free/daily_summary', methods=['GET'])
def get_daily_summary():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        today = datetime.utcnow().date()
        
        # Get logged meals for today
        meals = MealLog.query.filter_by(user_id=user_id, log_date=today).all()
        meals_list = [meal.to_dict() for meal in meals]
        
        # Calculate totals
        total_calories = sum(meal['calories'] for meal in meals_list)
        target_calories = user.daily_calories or 2000
        
        # Get one random tip
        import random
        daily_tip = random.choice(MOTIVATIONAL_TIPS)
        
        return jsonify({
            'date': today.isoformat(),
            'total_calories': total_calories,
            'target_calories': target_calories,
            'calorie_difference': target_calories - total_calories,
            'meals_count': len(meals_list),
            'daily_tip': daily_tip,
            'user_data': {
                'current_weight': user.current_weight,
                'weight_goal': user.weight_goal,
                'bmi': user.bmi
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Meal Swap Option
@app.route('/api/premium/meal-swap', methods=['POST'])
@require_premium
def get_meal_swap():
    try:
        user_id = session.get('user_id')
        
        data = request.get_json()
        current_meal = data.get('current_meal', '')
        calorie_target = data.get('calorie_target', 200)
        
        if not current_meal:
            return jsonify({'error': 'Current meal is required'}), 400
        
        # Check if model is available
        if model is None:
            return jsonify({
                'error': 'AI model not available'
            }), 500
        
        prompt = f"""Suggest alternative Pakistani meals similar to '{current_meal}' but with approximately {calorie_target} calories. 
        Keep the nutritional balance similar or better."""
        
        system_instruction = "You are a Pakistani nutritionist. Suggest alternative Pakistani meals similar to the current one but with different ingredients or preparation methods to achieve the target calories while maintaining nutritional balance."
        
        response = model.generate_content(f"{system_instruction} {prompt}")
        
        return jsonify({
            'current_meal': current_meal,
            'alternatives': response.text,
            'calorie_target': calorie_target
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Run the app
def start():
    # For development
    if __name__ == "__main__":
        app.run(debug=True, host='127.0.0.1', port=5000)
    else:
        # For production deployment
        app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))