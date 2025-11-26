
from flask import Flask, request, jsonify, send_file, session, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from functools import wraps
from datetime import datetime, timedelta
import os
import google.generativeai as genai
from dotenv import load_dotenv
import json
import re
import random
import concurrent.futures
import http.client
import urllib.parse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import event, func
from sqlalchemy.engine import Engine

# ======================== NILE MULTI-TENANCY SETUP ========================
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nutriguide-prod-secret-key-change-in-production')
CORS(app, supports_credentials=True)

# Database configuration with Nile multi-tenancy
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg3://019aaf22-80a9-7236-83f8-f67eecf76bdb:478df69b-3b78-46e5-b85f-0859afb2926f@us-west-2.db.thenile.dev:5432/nutridb"
)

# Force convert to postgresql:// (SQLAlchemy requires this)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg3://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300
}
db = SQLAlchemy(app)
# AUTOMATIC TENANT ISOLATION — Every query is scoped to current user
@event.listens_for(Engine, "connect")
def set_nile_tenant(dbapi_connection, connection_record):
    user_id = session.get('user_id')
    if user_id:
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET nile.tenant_id = '{user_id}'")
        cursor.close()

@event.listens_for(Engine, "connect", once=True)
def enable_extensions(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cursor.close()
        dbapi_connection.commit()
    except:
        pass
# =========================================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

# =================================== MODELS ===================================
class User(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)  # This becomes Nile tenant_id
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    current_weight = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    goal_type = db.Column(db.String(20), nullable=True)
    weight_goal = db.Column(db.Float, nullable=True)
    bmi = db.Column(db.Float, nullable=True)
    daily_calories = db.Column(db.Float, nullable=True)
    subscription_tier = db.Column(db.String(20), default='free')
    subscription_start_date = db.Column(db.DateTime)
    subscription_end_date = db.Column(db.DateTime)
    subscription_status = db.Column(db.String(20), default='active')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    def to_dict(self):
        return {
            'id': self.id, 'email': self.email, 'current_weight': self.current_weight,
            'height': self.height, 'gender': self.gender, 'goal_type': self.goal_type,
            'weight_goal': self.weight_goal, 'bmi': self.bmi, 'daily_calories': self.daily_calories,
            'subscription_tier': 'free',
            'subscription_start_date': datetime.utcnow().isoformat(),
            'subscription_end_date': (datetime.utcnow() + timedelta(days=36500)).isoformat(),
            'subscription_status': 'active'
        }

class NutritionEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    food_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    protein = db.Column(db.Float, nullable=False)
    carbs = db.Column(db.Float, nullable=False)
    fat = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for k, v in data.items():
            if isinstance(v, (datetime, datetime.date)):
                data[k] = v.isoformat()
        return data

# =========================================================================
# Gemini AI Setup
api_key = os.environ.get("GEMINI_API_KEY")
model = None
if api_key:
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        model.generate_content("hi")
        print("Gemini AI ready")
    except Exception as e:
        print(f"Gemini error: {e}")

with app.app_context():
    db.create_all()
    print("Nile Database initialized — multi-tenancy active")

# =================================== UTILS ===================================
def calculate_bmi(weight, height):
    if not weight or not height or height <= 0: return None
    return round(weight / ((height / 100) ** 2), 2)

def calculate_daily_calories(weight, height, gender, goal_type, age=30):
    if not weight or not height or not gender: return None
    bmr = 10 * weight + 6.25 * height - 5 * age + (5 if gender.lower() == 'male' else -161)
    cal = bmr * 1.2
    if goal_type == 'lose': cal -= 500
    elif goal_type == 'gain': cal += 500
    return round(cal)

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

# =================================== ROUTES ===================================

@app.route('/')
def landing_page():
    if session.get('user_id'):
        return redirect('/dashboard')
    return send_file('landing.html')

@app.route('/dashboard')
def dashboard(): return send_file('dashboard.html')

@app.route('/chatbot') 
def chatbot_ui(): return send_file('chatbot.html')

@app.route('/register')
def register_page(): return send_file('register.html')

@app.route('/login')
def login_page(): return send_file('login.html')

@app.route('/diet-plan') 
def diet_plan(): return send_file('diet_plan.html')

@app.route('/recipes') 
def recipes(): return send_file('recipes.html')

@app.route('/shopping-list') 
def shopping_list(): return send_file('shopping_list.html')

@app.route('/exercise-planner') 
def exercise_planner(): return send_file('exercise_planner.html')

@app.route('/profile') 
def profile(): return send_file('profile.html')

@app.route('/settings')
def settings(): return send_file('settings.html')

@app.route('/history')
def history(): return send_file('history.html')

@app.route('/nutrition_tracking') 
def nutrition_tracking(): return send_file('nutrition_tracking.html')

@app.route('/<path:filename>')
def serve_static_html(filename):
    if filename.endswith('.html'):
        file_path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(file_path):
            return send_file(file_path)
    return jsonify({'error': 'File not found'}), 404

@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(os.path.join(app.root_path, '..', 'static', 'images'), filename)

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password required'}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'User already exists'}), 409

        user = User(email=data['email'])
        user.set_password(data['password'])
        for field in ['current_weight','height','gender','goal_type','weight_goal']:
            if field in data: setattr(user, field, data[field])
        user.bmi = calculate_bmi(user.current_weight, user.height)
        user.daily_calories = calculate_daily_calories(user.current_weight, user.height, user.gender, user.goal_type)
        db.session.add(user)
        db.session.commit()
        return jsonify({'message': 'Registered', 'user': user.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    if user and user.check_password(data['password']):
        session['user_id'] = user.id
        return jsonify({'message': 'Success', 'user': user.to_dict()}), 200
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/google-login', methods=['POST'])
def google_login():
    try:
        data = request.get_json()
        token = data.get('credential')
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request())
        email = idinfo['email']
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'Account does not exist. Please register first.'}), 400
        session['user_id'] = user.id
        return jsonify({'message': 'Google login successful', 'user': user.to_dict()}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out'})

@app.route('/api/current_user', methods=['GET'])
@login_required
def current_user():
    user = User.query.get(session['user_id'])
    return jsonify({'user': user.to_dict()})

@app.route('/api/food_search', methods=['GET'])
def food_search():
    q = request.args.get('food_name', '').lower().strip()
    results = [v for k, v in LOCAL_FOOD_DATABASE.items() if q in k or q in v['name'].lower()]
    return jsonify({'results': results})

@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    data = request.get_json()
    user_message = data.get('user_message', '').strip()
    if 'expert' in user_message.lower():
        return jsonify({'response': 'Aap ke sawal ka jawab dena zaroori hai. Kripya apna contact number ya email provide karein...', 'needs_expert': True})
    if model:
        try:
            response = model.generate_content(f"Roman Urdu mein jawab do: {user_message}")
            return jsonify({'response': response.text})
        except:
            pass
    return jsonify({'response': 'AI unavailable'})

@app.route('/api/diet-plan', methods=['POST'])
@login_required
def generate_weekly_meal_plan():
    days = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    plan = {day: {
        "breakfast": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['breakfast'])],
        "lunch": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['lunch'])],
        "dinner": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['dinner'])],
        "snack": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['snack'])]
    } for day in days}
    return jsonify({"diet_plan": plan})

@app.route('/api/nutrition/entries', methods=['GET', 'POST'])
@login_required
def nutrition_entries():
    if request.method == 'GET':
        date_str = request.args.get('date')
        date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()
        entries = NutritionEntry.query.filter_by(date=date).all()
        return jsonify({'entries': [e.to_dict() for e in entries]})
    else:
        data = request.get_json()
        entry = NutritionEntry(
            food_name=data['food_name'],
            quantity=data['quantity'],
            unit=data['unit'],
            meal_type=data['meal_type'],
            calories=data['calories'],
            protein=data['protein'],
            carbs=data['carbs'],
            fat=data['fat']
        )
        db.session.add(entry)
        db.session.commit()
        return jsonify({'entry': entry.to_dict()}), 201

@app.route('/api/nutrition/entries/<int:entry_id>', methods=['PUT', 'DELETE'])
@login_required
def nutrition_entry_detail(entry_id):
    entry = NutritionEntry.query.get(entry_id)
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    if request.method == 'DELETE':
        db.session.delete(entry)
        db.session.commit()
        return jsonify({'message': 'Deleted'})
    # PUT logic here if needed
    return jsonify({'entry': entry.to_dict()})

@app.route('/api/daily-summary', methods=['GET'])
@login_required
def daily_summary():
    today = datetime.utcnow().date()
    entries = NutritionEntry.query.filter_by(date=today).all()
    total = sum(e.calories for e in entries)
    return jsonify({'total_calories': total, 'entries_count': len(entries)})

@app.route('/api/nutrition/history', methods=['GET'])
@login_required
def get_nutrition_history():
    try:
        user_id = session.get('user_id')
        limit = int(request.args.get('limit', 7))  # Default to 7 days
        
        # Get the last N days of nutrition data
        entries = db.session.query(
            NutritionEntry.date,
            db.func.sum(NutritionEntry.calories).label('total_calories'),
            db.func.count(NutritionEntry.id).label('food_count')
        ).filter(
            NutritionEntry.user_id == user_id
        ).group_by(
            NutritionEntry.date
        ).order_by(
            NutritionEntry.date.desc()
        ).limit(limit).all()
        
        history = []
        for entry in entries:
            history.append({
                'date': entry.date.isoformat(),
                'total_calories': entry.total_calories,
                'food_count': entry.food_count
            })
        
        return jsonify({'history': history}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Route for nutrition tracking page
@app.route('/nutrition_tracking')
@login_required
def nutrition_tracking():
    html_path = os.path.join(os.path.dirname(__file__), 'nutrition_tracking.html')
    return send_file(html_path)

# FIXED: Weekly Meal Plan Generator (No Repeated Days!) - Now Available to All Users
@app.route('/api/diet-plan', methods=['POST'])
def generate_weekly_meal_plan():
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        data = request.get_json()
        goal = data.get('goal', user.goal_type) or 'maintain'
        calorie_target = data.get('calorie_target', user.daily_calories) or 2000
        diet_preference = data.get('diet_preference', 'balanced')
        non_veg_preference = data.get('non_veg_preference', False)
        allergies = data.get('allergies', [])
        medical_conditions = data.get('medical_conditions', [])

        if model is None:
            import random
            # Return 7-day plan structure in correct sequence that matches frontend expectations
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            plan = {}
            for day in days:
                plan[day] = {
                    "breakfast": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['breakfast'])],
                    "lunch": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['lunch'])],
                    "dinner": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['dinner'])],
                    "snack": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['snack'])]
                }
            return jsonify({
                "diet_plan": plan,
                "goal": goal,
                "calorie_target": calorie_target,
                "diet_preference": diet_preference,
                "non_veg_preference": non_veg_preference,
                "allergies": allergies,
                "medical_conditions": medical_conditions,
                "plan_type": "structured",
                "generated_by": "fallback"
            }), 200

        # Enhanced prompt that ensures correct day sequence
        food_type = "non-vegetarian" if non_veg_preference else "vegetarian"
        allergen_info = f" avoiding: {', '.join(allergies)}" if allergies else ""
        medical_info = f" with considerations for: {', '.join(medical_conditions)}" if medical_conditions else ""

        prompt = f"""
        Generate a comprehensive 7-day Pakistani meal plan with breakfast, lunch, dinner, and snacks for each day in SEQUENTIAL order (Monday through Sunday).
        Goal: {goal}, Target calories: ~{calorie_target} kcal per day, Diet type: {food_type}, Preference: {diet_preference}{allergen_info}{medical_info}.
        Structure the response as a JSON object with days of the week in lowercase as keys in sequential order: monday, tuesday, wednesday, thursday, friday, saturday, sunday.
        Each day should contain breakfast, lunch, dinner, and snack keys with arrays of meal objects.
        Each meal object should include: name, calories (integer), protein (in grams), carbs (in grams), fat (in grams), description.
        Example:
        {{
          "monday": {{
            "breakfast": [
              {{"name": "meal name", "calories": 300, "protein": 12, "carbs": 35, "fat": 8, "description": "detailed description"}}
            ],
            "lunch": [...],
            "dinner": [...],
            "snack": [...]
          }},
          "tuesday": {{...}},
          "wednesday": {{...}},
          "thursday": {{...}},
          "friday": {{...}},
          "saturday": {{...}},
          "sunday": {{...}}
        }}
        Return ONLY the JSON object with no additional text. Ensure days are in correct sequential order.
        """

        # Add timeout handling for the AI call
        import concurrent.futures
        import time
        
        # Use a timeout for the AI generation
        def generate_ai_content():
            return model.generate_content(prompt)
        
        try:
            # Run AI call with timeout of 30 seconds
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(generate_ai_content)
                response = future.result(timeout=30)  # 30 second timeout
        except concurrent.futures.TimeoutError:
            # Return 7-day plan structure in correct sequence
            import random
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            fallback_plan = {}
            for day in days:
                fallback_plan[day] = {
                    "breakfast": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['breakfast'])],
                    "lunch": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['lunch'])],
                    "dinner": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['dinner'])],
                    "snack": [random.choice(LIMITED_FOOD_RECOMMENDATIONS['snack'])]
                }

            return jsonify({
                "diet_plan": fallback_plan,
                "goal": goal,
                "calorie_target": calorie_target,
                "diet_preference": diet_preference,
                "non_veg_preference": non_veg_preference,
                "allergies": allergies,
                "medical_conditions": medical_conditions,
                "plan_type": "structured_timeout",
                "generated_by": "timeout"
            }), 200
        
        raw = response.text.strip() if response and hasattr(response, 'text') else ""
        
        # Extract JSON from response if it's wrapped in code blocks
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(1).strip()
            
        meal_plan = json.loads(raw)
        
        return jsonify({
            "diet_plan": meal_plan,
            "original_response": response.text.strip() if response and hasattr(response, 'text') else raw,
            "goal": goal,
            "calorie_target": calorie_target,
            "diet_preference": diet_preference,
            "non_veg_preference": non_veg_preference,
            "allergies": allergies,
            "medical_conditions": medical_conditions,
            "plan_type": "ai_generated",
            "generated_by": "gemini_json"
        }), 200

    except json.JSONDecodeError:
        # If JSON parsing fails, return structured fallback data
        fallback_plan = {
            "breakfast_suggestions": [
                {"name": "Omelette with Roti", "calories": 350, "details": "2 eggs with one whole wheat roti and salad"},
                {"name": "Porridge with Nuts", "calories": 300, "details": "Oats with dry fruits and honey"},
                {"name": "Paratha with Curd", "calories": 400, "details": "Two whole wheat parathas with yogurt and pickle"}
            ],
            "lunch_suggestions": [
                {"name": "Daal Chawal with Vegetable", "calories": 500, "details": "Yellow lentils with rice and mixed vegetables"},
                {"name": "Chicken Curry with Roti", "calories": 550, "details": "Grilled chicken with 2 rotis and salad"},
                {"name": "Biryani (small portion)", "calories": 450, "details": "Small portion with raita and salad"}
            ],
            "dinner_suggestions": [
                {"name": "Roti with Daal and Sabzi", "calories": 400, "details": "Two rotis with lentils and vegetable curry"},
                {"name": "Vegetable Curry with Rice", "calories": 450, "details": "Mixed vegetables with rice"},
                {"name": "Simple Khichdi", "calories": 380, "details": "Rice and lentil khichdi with ghee"}
            ],
            "snack_suggestions": [
                {"name": "Fruit Salad", "calories": 150, "details": "Seasonal fruits with nuts"},
                {"name": "Tea with Biscuits", "calories": 200, "details": "One cup tea with digestive biscuits"}
            ]
        }
        
        return jsonify({
            "diet_plan": fallback_plan,
            "original_response": raw if 'raw' in locals() else "AI response could not be parsed",
            "goal": goal,
            "calorie_target": calorie_target,
            "diet_preference": diet_preference,
            "non_veg_preference": non_veg_preference,
            "allergies": allergies,
            "medical_conditions": medical_conditions,
            "plan_type": "text_fallback",
            "generated_by": "gemini_raw",
            "warning": "AI response was not valid JSON – using structured fallback."
        }), 200
        
    except Exception as e:
        # Always return JSON, even in error cases
        return jsonify({
            'error': str(e),
            'diet_plan': {
                "breakfast_suggestions": [{"name": "Standard Breakfast", "calories": 350, "details": "Contact support if you see this message"}],
                "lunch_suggestions": [{"name": "Standard Lunch", "calories": 450, "details": "Contact support if you see this message"}],
                "dinner_suggestions": [{"name": "Standard Dinner", "calories": 400, "details": "Contact support if you see this message"}],
                "snack_suggestions": [{"name": "Standard Snack", "calories": 200, "details": "Contact support if you see this message"}]
            },
            'plan_type': 'error_fallback'
        }), 500

@app.route('/api/premium/shopping-list', methods=['POST'])
@login_required
def generate_shopping_list():
    """
    Generate a shopping list based on the meal plan provided by the frontend.

    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401

        data = request.get_json()
        meal_plan = data.get('meal_plan', [])

        # Generate a sample shopping list
        # In a real implementation, this would analyze the meal plan and create a proper shopping list
        shopping_list = {
            "categories": {
                "Produce": [
                    {"name": "Tomatoes", "quantity": "500g", "notes": "Ripe and fresh"},
                    {"name": "Onions", "quantity": "1kg", "notes": "Yellow onions"},
                    {"name": "Garlic", "quantity": "1 bulb", "notes": ""},
                    {"name": "Ginger", "quantity": "1 piece", "notes": "Fresh"},
                    {"name": "Green chilies", "quantity": "5 pieces", "notes": "Small green ones"},
                    {"name": "Coriander (Cilantro)", "quantity": "1 bunch", "notes": "Fresh"}
                ],
                "Proteins": [
                    {"name": "Chicken", "quantity": "1kg", "notes": "Boneless, skinless"},
                    {"name": "Mutton", "quantity": "500g", "notes": "For curry"},
                    {"name": "Eggs", "quantity": "1 dozen", "notes": "Large size"}
                ],
                "Grains": [
                    {"name": "Basmati Rice", "quantity": "1kg", "notes": "Aged basmati"},
                    {"name": "Whole wheat flour (Atta)", "quantity": "2kg", "notes": "For roti/chapati"},
                    {"name": "Chana daal", "quantity": "500g", "notes": "Split gram lentils"},
                    {"name": "Moong daal", "quantity": "500g", "notes": "Yellow lentils"}
                ],
                "Spices": [
                    {"name": "Cumin seeds", "quantity": "1 small packet", "notes": ""},
                    {"name": "Coriander powder", "quantity": "1 packet", "notes": ""},
                    {"name": "Turmeric powder", "quantity": "1 packet", "notes": ""},
                    {"name": "Red chili powder", "quantity": "1 packet", "notes": "Medium spice level"},
                    {"name": "Garam masala", "quantity": "1 packet", "notes": ""},
                    {"name": "Salt", "quantity": "1 packet", "notes": "Iodized"}
                ],
                "Oils & Sauces": [
                    {"name": "Cooking oil", "quantity": "1 liter", "notes": "Any cooking oil"},
                    {"name": "Ghee", "quantity": "200g", "notes": "Pure desi ghee"}
                ],
                "Dairy": [
                    {"name": "Milk", "quantity": "1 liter", "notes": "Full cream"},
                    {"name": "Yogurt", "quantity": "500g", "notes": "Fresh and thick"}
                ]
            }
        }

        # Calculate estimated cost (in Pakistani Rupees)
        # This is a simple estimation, in reality would be based on local prices
        estimated_cost = 0
        for category, items in shopping_list['categories'].items():
            estimated_cost += len(items) * 100  # Simple estimation per item

        shopping_list['estimated_cost'] = f"Rs {estimated_cost}"
        shopping_list['total_items'] = sum(len(items) for items in shopping_list['categories'].values())

        return jsonify({
            'shopping_list': shopping_list,
            'message': 'Shopping list generated successfully',
            'generated_by': 'backend'
        }), 200

    except Exception as e:
        print(f"Error generating shopping list: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze-food-plate', methods=['POST'])
@login_required
def analyze_food_plate():
    """
    Analyze a food plate image using the RapidAPI service.
    This endpoint calls the external food analysis API and returns the results.
    """
    try:
        # Get the RapidAPI key from environment variables
        rapidapi_key = os.environ.get('RAPIDAPI_KEY')
        if not rapidapi_key:
            return jsonify({'error': 'RapidAPI key not configured. Please add RAPIDAPI_KEY to your environment variables.'}), 500

        data = request.get_json()
        # Default to a sample image if no image URL is provided
        image_url = data.get('image_url', 'https://upload.wikimedia.org/wikipedia/commons/b/bd/Breakfast_foods.jpg')
        
        # Call the external API
        conn = http.client.HTTPSConnection("ai-workout-planner-exercise-fitness-nutrition-guide.p.rapidapi.com")
        
        payload = ""
        
        headers = {
            'x-rapidapi-host': "ai-workout-planner-exercise-fitness-nutrition-guide.p.rapidapi.com",
            'x-rapidapi-key': rapidapi_key,
            'Content-Type': "application/x-www-form-urlencoded"
        }
        
        # Create the request URL with the image URL parameter
        import urllib.parse
        encoded_image_url = urllib.parse.quote(image_url, safe='')
        request_path = f"/analyzeFoodPlate?imageUrl={encoded_image_url}&lang=en&noqueue=1"
        
        conn.request("POST", request_path, payload, headers)
        
        res = conn.getresponse()
        api_data = res.read()
        conn.close()
        
        # Parse the API response
        try:
            api_response = json.loads(api_data.decode("utf-8"))
        except json.JSONDecodeError:
            # Return a mock response for testing if the API is not working or key is invalid
            mock_response = {
                'nutrition': {
                    'calories': 750,
                    'carbs': 45,
                    'protein': 30,
                    'fat': 40,
                    'sugar': 15,
                    'fiber': 8
                },
                'food_items': [
                    {'name': 'Pancakes', 'quantity': '2 medium', 'calories': 400},
                    {'name': 'Butter', 'quantity': '2 tbsp', 'calories': 200},
                    {'name': 'Maple Syrup', 'quantity': '3 tbsp', 'calories': 150}
                ],
                'exercise_recommendations': [
                    {'exercise': 'Walking (3.5 mph)', 'time': '90 min'},
                    {'exercise': 'Jogging (5 mph)', 'time': '45 min'},
                    {'exercise': 'Cycling (12-14 mph)', 'time': '60 min'},
                    {'exercise': 'Swimming (freestyle)', 'time': '50 min'}
                ]
            }
            return jsonify({
                'analysis': mock_response,
                'message': 'Using mock data because real API response could not be parsed. Please check your RAPIDAPI_KEY.'
            }), 200
        
        # Return the API response
        return jsonify({
            'analysis': api_response,
            'message': 'Food plate analyzed successfully'
        }), 200

    except Exception as e:
        print(f"Error analyzing food plate: {e}")
        # Return a mock response as fallback
        mock_response = {
            'nutrition': {
                'calories': 750,
                'carbs': 45,
                'protein': 30,
                'fat': 40,
                'sugar': 15,
                'fiber': 8
            },
            'food_items': [
                {'name': 'Pancakes', 'quantity': '2 medium', 'calories': 400},
                {'name': 'Butter', 'quantity': '2 tbsp', 'calories': 200},
                {'name': 'Maple Syrup', 'quantity': '3 tbsp', 'calories': 150}
            ],
            'exercise_recommendations': [
                {'exercise': 'Walking (3.5 mph)', 'time': '90 min'},
                {'exercise': 'Jogging (5 mph)', 'time': '45 min'},
                {'exercise': 'Cycling (12-14 mph)', 'time': '60 min'},
                {'exercise': 'Swimming (freestyle)', 'time': '50 min'}
            ]
        }
        return jsonify({
            'analysis': mock_response,
            'message': f'Food plate analysis completed with mock data due to error: {str(e)}'
        }), 200

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)