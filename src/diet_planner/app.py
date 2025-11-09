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
app.secret_key = os.environ.get('SECRET_KEY', 'nutriguide-prod-secret-key-change-in-production')
CORS(app, supports_credentials=True)

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, '..', '..', 'database.db')}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    current_weight = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    goal_type = db.Column(db.String(20), nullable=True)
    weight_goal = db.Column(db.Float, nullable=True)
    bmi = db.Column(db.Float, nullable=True)
    daily_calories = db.Column(db.Float, nullable=True)
    subscription_tier = db.Column(db.String(20), nullable=True, default='free')
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    subscription_status = db.Column(db.String(20), nullable=True, default='inactive')

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
        genai.configure(api_key=api_key)

        available_models = []
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            print(f"Available models: {available_models}")
        except Exception as e:
            print(f"Error listing models: {e}")

        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            test_response = model.generate_content("Hello")
            print("Gemini model (gemini-2.5-flash) configured successfully")
        except Exception as model_error:
            print(f"Error with gemini-2.5-flash: {model_error}")
            try:
                model = genai.GenerativeModel('gemini-2.5-pro')
                test_response = model.generate_content("Hello")
                print("Gemini model (gemini-2.5-pro) configured successfully")
            except Exception as pro_error:
                print(f"Error with gemini-2.5-pro: {pro_error}")
                try:
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
    db.create_all()
    print("Database tables created successfully")
    print(f"User model has the following fields: {[column.name for column in User.__table__.columns]}")
    try:
        test_user = User.query.first()
        print("Database connection successful. Found existing users:", test_user is not None)
    except Exception as e:
        print(f"Database connection test failed: {e}")
        print("Recreating database due to schema mismatch...")
        db.drop_all()
        db.create_all()
        print("Database recreated successfully")

def calculate_bmi(weight, height):
    if not weight or not height or height <= 0:
        return None
    height_m = height / 100
    bmi = weight / (height_m * height_m)
    return round(bmi, 2)

def calculate_daily_calories(weight, height, gender, goal_type, age=30):
    if not weight or not height or not gender:
        return None
    if gender.lower() == 'male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    elif gender.lower() == 'female':
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    activity_factor = 1.2
    if goal_type == 'lose':
        daily_calories = bmr * activity_factor - 500
    elif goal_type == 'gain':
        daily_calories = bmr * activity_factor + 500
    else:
        daily_calories = bmr * activity_factor
    return round(daily_calories)

# Registration route
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400
        existing_user = User.query.filter_by(email=data['email']).first()
        if existing_user:
            return jsonify({'error': 'User with this email already exists'}), 409
        weight = data.get('current_weight')
        height = data.get('height')
        gender = data.get('gender')
        goal_type = data.get('goal_type')
        bmi = calculate_bmi(weight, height)
        daily_calories = calculate_daily_calories(weight, height, gender, goal_type)
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
        return jsonify({'message': 'User registered successfully', 'user': user.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Local food database
LOCAL_FOOD_DATABASE = {
    'roti': {'name': 'Roti', 'calories': 70, 'carbs': 15, 'protein': 3, 'fat': 0.5},
    'biryani': {'name': 'Biryani', 'calories': 250, 'carbs': 35, 'protein': 8, 'fat': 10},
    'daal': {'name': 'Daal (Lentils)', 'calories': 120, 'carbs': 20, 'protein': 9, 'fat': 2},
    'rice': {'name': 'Rice', 'calories': 200, 'carbs': 45, 'protein': 4, 'fat': 0.5},
    'chicken': {'name': 'Chicken', 'calories': 165, 'carbs': 0, 'protein': 31, 'fat': 3.6},
    'kheer': {'name': 'Kheer', 'calories': 150, 'carbs': 28, 'protein': 4, 'fat': 2},
    'egg': {'name': 'Egg', 'calories': 70, 'carbs': 0.6, 'protein': 6, 'fat': 5},
    'aloo': {'name': 'Aloo (Potato)', 'calories': 77, 'carbs': 17, 'protein': 2, 'fat': 0.1},
    'gobi': {'name': 'Gobi (Cauliflower)', 'calories': 25, 'carbs': 5, 'protein': 2, 'fat': 0.3},
    'mix_vegetable': {'name': 'Mixed Vegetables', 'calories': 45, 'carbs': 8, 'protein': 2, 'fat': 0.4},
    'paratha': {'name': 'Paratha', 'calories': 150, 'carbs': 20, 'protein': 4, 'fat': 6}
}

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

FREE_USER_MEAL_LIMIT = 5

@app.route('/api/food_search', methods=['GET'])
def food_search():
    try:
        food_name = request.args.get('food_name', '').lower().strip()
        if not food_name:
            return jsonify({'error': 'Food name parameter is required'}), 400
        result = []
        for key, value in LOCAL_FOOD_DATABASE.items():
            if food_name in key or food_name in value['name'].lower():
                result.append(value)
        if not result:
            return jsonify({'message': f'No food items found matching "{food_name}"'}), 404
        return jsonify({'results': result, 'count': len(result)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    try:
        data = request.get_json()
        user_message = data.get('user_message', '').strip()
        if not user_message:
            return jsonify({'error': 'User message is required'}), 400
        if 'Mujhe expert se baat karni hai' in user_message:
            return jsonify({'response': 'Aap ke sawal ka jawab dena zaroori hai. Kripya apna contact number ya email provide karein taake hum aap se expert ke through rabta kar sakein.', 'needs_expert': True}), 200
        if model is None:
            return jsonify({'response': 'Sorry, the AI model is not available. Please contact the administrator.', 'needs_expert': False}), 500
        system_instruction = "Aap Pakistani diet aur health matters par baat karne wale nutritionist hain. Jawab Roman Urdu mein dena. Sirf Pakistani diet, traditional foods, aur health concerns par bat karna. Koi bhi non-Pakistani diet ya western foods ke baare mein bat karne se mana karna. jawab chota hoga, seedha aur asan alfaaz mein jawab dein."
        try:
            response = model.generate_content(f"{system_instruction} User ka sawal: {user_message}")
            bot_response = response.text if response and hasattr(response, 'text') else "Maaf kijiye, aapka sawal samajh nahi aaya. Kripya din mein Pakistani khana ya sehat ke bare mein pochhein."
        except Exception as gen_error:
            print(f"Error generating content: {gen_error}")
            bot_response = f"Sorry, I'm having trouble generating a response. Error: {str(gen_error)}"
        return jsonify({'response': bot_response, 'needs_expert': False}), 200
    except Exception as e:
        print(f"Error in chatbot endpoint: {e}")
        return jsonify({'error': str(e)}), 500

# Static HTML Routes
@app.route('/')
def landing_page():
    user_id = session.get('user_id')
    if user_id:
        return redirect(url_for('dashboard'))
    else:
        html_path = os.path.join(os.path.dirname(__file__), 'landing.html')
        return send_file(html_path)

@app.route('/dashboard')
@login_required
def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
    return send_file(html_path)

@app.route('/chatbot')
@login_required
def chatbot_ui():
    html_path = os.path.join(os.path.dirname(__file__), 'chatbot.html')
    return send_file(html_path)

@app.route('/register')
def register_page():
    html_path = os.path.join(os.path.dirname(__file__), 'register.html')
    return send_file(html_path)

@app.route('/login')
def login_page():
    html_path = os.path.join(os.path.dirname(__file__), 'login.html')
    return send_file(html_path)

@app.route('/diet-plan')
@login_required
def diet_plan():
    html_path = os.path.join(os.path.dirname(__file__), 'diet_plan.html')
    return send_file(html_path)

@app.route('/recipes')
@login_required
def recipes():
    html_path = os.path.join(os.path.dirname(__file__), 'recipes.html')
    return send_file(html_path)

@app.route('/shopping-list')
@login_required
def shopping_list():
    html_path = os.path.join(os.path.dirname(__file__), 'shopping_list.html')
    return send_file(html_path)

@app.route('/<path:filename>')
def serve_static_html(filename):
    if filename.endswith('.html'):
        file_path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(file_path):
            return send_file(file_path)
        else:
            return jsonify({'error': 'File not found'}), 404
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(os.path.join(app.root_path, '..', 'static', 'images'), filename)

# Auth Routes
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400
        user = User.query.filter_by(email=data['email']).first()
        if not user or not user.check_password(data['password']):
            return jsonify({'error': 'Invalid email or password'}), 401
        session['user_id'] = user.id
        return jsonify({'message': 'Login successful', 'user': user.to_dict()}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    try:
        session.pop('user_id', None)
        return jsonify({'message': 'Logout successful'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/current_user', methods=['GET'])
def current_user():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({'message': 'User info retrieved successfully', 'user': user.to_dict()}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Subscription System
SUBSCRIPTION_PLANS = {
    'pro_monthly': {'name': 'Pro Monthly', 'price': 500, 'duration': 30, 'features': [...]},
    'pro_yearly': {'name': 'Pro Yearly', 'price': 1500, 'duration': 365, 'features': [...]}
}

@app.route('/api/subscription/plans', methods=['GET'])
def get_subscription_plans():
    return jsonify({'plans': SUBSCRIPTION_PLANS}), 200

@app.route('/api/subscription/create', methods=['POST'])
def create_subscription():
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({'error': 'User not authenticated'}), 401
        user = User.query.get(user_id)
        if not user: return jsonify({'error': 'User not found'}), 404
        data = request.get_json()
        plan_id = data.get('plan_id')
        if not plan_id or plan_id not in SUBSCRIPTION_PLANS:
            return jsonify({'error': 'Invalid plan ID'}), 400
        plan = SUBSCRIPTION_PLANS[plan_id]
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=plan['duration'])
        user.subscription_tier = 'pro'
        user.subscription_start_date = start_date
        user.subscription_end_date = end_date
        user.subscription_status = 'active'
        db.session.commit()
        return jsonify({'message': 'Subscription created successfully', 'plan': plan, 'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/subscription/status', methods=['GET'])
def get_subscription_status():
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({'error': 'User not authenticated'}), 401
        user = User.query.get(user_id)
        if not user: return jsonify({'error': 'User not found'}), 404
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

@app.route('/api/subscription/cancel', methods=['POST'])
def cancel_subscription():
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({'error': 'User not authenticated'}), 401
        user = User.query.get(user_id)
        if not user: return jsonify({'error': 'User not found'}), 404
        user.subscription_status = 'inactive'
        db.session.commit()
        return jsonify({'message': 'Subscription cancelled successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def require_premium(func):
    def wrapper(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id: return jsonify({'error': 'User not authenticated'}), 401
        user = User.query.get(user_id)
        if not user: return jsonify({'error': 'User not found'}), 404
        if user.subscription_status != 'active':
            return jsonify({'error': 'Premium subscription required for this feature'}), 402
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# FIXED: Weekly Meal Plan Generator (No Repeated Days!)
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

        if model is None:
            import random
            breakfast = random.sample(LIMITED_FOOD_RECOMMENDATIONS['breakfast'], 7)
            dinner = random.sample(LIMITED_FOOD_RECOMMENDATIONS['dinner'], 7)
            plan = {
                "Monday":    {"breakfast": breakfast[0], "dinner": dinner[0]},
                "Tuesday":   {"breakfast": breakfast[1], "dinner": dinner[1]},
                "Wednesday": {"breakfast": breakfast[2], "dinner": dinner[2]},
                "Thursday":  {"breakfast": breakfast[3], "dinner": dinner[3]},
                "Friday":    {"breakfast": breakfast[4], "dinner": dinner[4]},
                "Saturday":  {"breakfast": breakfast[5], "dinner": dinner[5]},
                "Sunday":    {"breakfast": breakfast[6], "dinner": dinner[6]},
            }
            return jsonify({
                "meal_plan": plan,
                "goal": goal,
                "calorie_target": calorie_target,
                "non_veg_preference": non_veg_preference,
                "generated_by": "fallback"
            }), 200

        food_type = "non-vegetarian" if non_veg_preference else "vegetarian"
        prompt = f"""
        Generate a **single** 7-day Pakistani meal plan (breakfast + dinner only) for a
        {food_type} diet, daily calorie target approximately {calorie_target} kcal, goal = {goal}.

        Return **only** a JSON object with the exact keys:
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday".

        Each value must be an object with two keys:
        - "breakfast": {{ "name": "...", "calories": <int> }}
        - "dinner":   {{ "name": "...", "calories": <int> }}

        Do NOT repeat the day name inside the meal description.
        Do NOT add any extra text, markdown, or explanations.
        """

        response = model.generate_content(prompt)
        raw = response.text.strip()
        try:
            meal_plan = json.loads(raw)
        except json.JSONDecodeError:
            return jsonify({
                "meal_plan": raw,
                "goal": goal,
                "calorie_target": calorie_target,
                "non_veg_preference": non_veg_preference,
                "generated_by": "gemini_raw",
                "warning": "AI response was not valid JSON – returned as plain text."
            }), 200

        return jsonify({
            "meal_plan": meal_plan,
            "goal": goal,
            "calorie_target": calorie_target,
            "non_veg_preference": non_veg_preference,
            "generated_by": "gemini_json"
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# [Rest of your code below remains unchanged — macro tracker, meals, diet plan, etc.]
# ... (all other endpoints remain exactly as in your original code)

# Run the app
def start():
    if __name__ == "__main__":
        app.run(debug=True, host='127.0.0.1', port=5000)
    else:
        app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))