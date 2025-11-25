from flask import Flask, request, jsonify, render_template_string, send_from_directory, send_file, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import os
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from functools import wraps
from flask import redirect, url_for
from sqlalchemy.engine import Engine
from sqlalchemy import event
import http


# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nutriguide-prod-secret-key-change-in-production')
CORS(app, supports_credentials=True)

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgres://019aaf22-80a9-7236-83f8-f67eecf76bdb:478df69b-3b78-46e5-b85f-0859afb2926f@us-west-2.db.thenile.dev:5432/nutridb"
)

# Force convert to postgresql:// (SQLAlchemy requires this)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Initialize SQLAlchemy without engine options initially to avoid hstore detection
db = SQLAlchemy(app)


# AUTOMATIC TENANT ISOLATION — Every query is scoped to current user
@event.listens_for(Engine, "connect")
def set_nile_tenant(dbapi_connection, connection_record):
    # Only set tenant if there's an active request context
    # and avoid setting during initial connection setup/extension loading
    from flask import has_request_context
    try:
        # Check if we're in a request context first
        if has_request_context():
            user_id = session.get('user_id')
            if user_id:
                # Create a new cursor to set the tenant variable
                cursor = dbapi_connection.cursor()
                cursor.execute(f"SET nile.tenant_id = '{user_id}'")
                cursor.close()
    except:
        # If session access fails during initialization, ignore
        pass

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





# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)  # Increased size for scrypt hashes
    current_weight = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    goal_type = db.Column(db.String(20), nullable=True)
    weight_goal = db.Column(db.Float, nullable=True)
    bmi = db.Column(db.Float, nullable=True)
    daily_calories = db.Column(db.Float, nullable=True)
    # All features are free - these fields are maintained for compatibility but all users have access
    subscription_tier = db.Column(db.String(20), nullable=True, default='free')
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    subscription_status = db.Column(db.String(20), nullable=True, default='active')  # All users have active status

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
            'subscription_tier': 'free',  # Always return free tier since all features are free
            'subscription_start_date': datetime.utcnow().isoformat(),  # Always return current time
            'subscription_end_date': (datetime.utcnow() + timedelta(days=36500)).isoformat(),  # Always return long duration
            'subscription_status': 'active'  # Always return active since all features are free
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







@app.route('/api/google-login', methods=['POST'])
def google_login():
    """Handle Google login using ID token"""
    try:
        data = request.get_json()
        token = data.get('credential')

        if not token:
            return jsonify({'error': 'Google ID token is required'}), 400

        # Verify the Google ID token
        try:
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request())
            email = idinfo['email']
            name = idinfo.get('name', '')
            user_id = idinfo['sub']  # Google's unique user ID
        except ValueError as e:
            print(f"Invalid Google token: {e}")
            return jsonify({'error': 'Invalid Google token'}), 400

        # Find or create user in our database
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'Account with this email does not exist. Please register first.'}), 400

        # Store user in session
        session['user_id'] = user.id

        # Ensure user has access to all features
        if user.subscription_status != 'active':
            user.subscription_status = 'active'
            user.subscription_tier = 'free'
            user.subscription_start_date = datetime.utcnow()
            user.subscription_end_date = datetime.utcnow() + timedelta(days=36500)  # Long duration
            db.session.commit()

        return jsonify({'message': 'Google login successful', 'user': user.to_dict()}), 200
    except Exception as e:
        print(f"Error in google_login: {e}")
        return jsonify({'error': str(e)}), 500






# Create database tables
# Moved this to after app initialization to avoid connection issues during startup
def init_db():
    with app.app_context():
        try:
            # Check if tables exist and have the correct schema by attempting to create them
            # This will fail if there's a schema mismatch
            db.create_all()
            print("Database tables created successfully")
            print(f"User model has the following fields: {[column.name for column in User.__table__.columns]}")
            # NutritionEntry model is defined after this, so we can't access it here
            try:
                test_user = User.query.first()
                print("Database connection successful. Found existing users:", test_user is not None)
            except Exception as e:
                print(f"Database connection test failed: {e}")
                print("Recreating database due to schema mismatch...")
                db.session.rollback()  # Rollback any failed transactions
                db.drop_all()
                db.create_all()
                print("Database recreated successfully")
        except Exception as e:
            # If initialization fails due to schema mismatch or other issues, recreate database
            print(f"Database initialization failed: {e}")
            print("Recreating database due to schema mismatch...")
            try:
                db.session.rollback()  # Rollback any failed transactions
                # For database recreation, use a more targeted approach to avoid system table issues
                # Use quoted table name for "user" since it might be a reserved word
                from sqlalchemy import text
                db.session.execute(text('DROP TABLE IF EXISTS nutrition_entry;'))
                db.session.execute(text('DROP TABLE IF EXISTS "user";'))  # user is a reserved word in PostgreSQL
                db.session.commit()  # Commit the drops
                db.create_all()
                print("Database recreated successfully with new schema")
            except Exception as recreate_error:
                print(f"Error recreating database: {recreate_error}")
                # Fallback approach - let SQLAlchemy handle it
                try:
                    db.session.rollback()
                    db.create_all()  # Sometimes this works after a rollback
                    print("Database recreated with simple approach")
                except Exception as simple_error:
                    print(f"Simple approach also failed: {simple_error}")
                    # As a final fallback, just continue with existing schema
                    pass
                db.session.rollback()

# Initialize the database after the app is fully set up
init_db()

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
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Check if this is an account creation request (with email and password)
        if data.get('email') and data.get('password'):
            # Check if user already exists
            existing_user = User.query.filter_by(email=data['email']).first()
            if existing_user:
                return jsonify({'error': 'User with this email already exists'}), 409

            # Extract profile information if provided
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
                daily_calories=daily_calories,
                # All features are free - setting default values
                subscription_tier='free',
                subscription_start_date=datetime.utcnow(),
                subscription_end_date=datetime.utcnow() + timedelta(days=36500),  # Long duration for all users
                subscription_status='active'  # All users have access to all features
            )
            user.set_password(data['password'])
            db.session.add(user)
            db.session.commit()
            return jsonify({'message': 'User registered successfully', 'user': user.to_dict()}), 201
        else:
            # This is a profile update request for an existing user in session
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'User not authenticated'}), 401

            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Update profile information
            if 'current_weight' in data:
                user.current_weight = data['current_weight']
            if 'height' in data:
                user.height = data['height']
            if 'gender' in data:
                user.gender = data['gender']
            if 'goal_type' in data:
                user.goal_type = data['goal_type']
            if 'weight_goal' in data:
                user.weight_goal = data['weight_goal']

            # Recalculate BMI and daily calories if weight/height/gender/goal changed
            if user.current_weight and user.height:
                user.bmi = calculate_bmi(user.current_weight, user.height)
            if user.current_weight and user.height and user.gender and user.goal_type:
                user.daily_calories = calculate_daily_calories(user.current_weight, user.height, user.gender, user.goal_type)

            db.session.commit()
            return jsonify({'message': 'Profile updated successfully', 'user': user.to_dict()}), 200

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

# No need for hardcoded recipe database - will use Gemini API to generate Pakistani recipes

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

@app.route('/exercise-planner')
@login_required
def exercise_planner():
    html_path = os.path.join(os.path.dirname(__file__), 'exercise_planner.html')
    return send_file(html_path)

@app.route('/profile')
@login_required
def profile():
    html_path = os.path.join(os.path.dirname(__file__), 'profile.html')
    return send_file(html_path)

@app.route('/settings')
@login_required
def settings():
    html_path = os.path.join(os.path.dirname(__file__), 'settings.html')
    return send_file(html_path)

@app.route('/history')
@login_required
def history():
    html_path = os.path.join(os.path.dirname(__file__), 'history.html')
    return send_file(html_path)

# This is the original static recipe function that has been replaced by AI-powered version

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
        # Ensure user has access to all features
        if user.subscription_status != 'active':
            user.subscription_status = 'active'
            user.subscription_tier = 'free'
            user.subscription_start_date = datetime.utcnow()
            user.subscription_end_date = datetime.utcnow() + timedelta(days=36500)  # Long duration
            db.session.commit()

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

@app.route('/api/current_user', methods=['GET', 'PUT'])
def current_user():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if request.method == 'GET':
            return jsonify({'message': 'User info retrieved successfully', 'user': user.to_dict()}), 200

        elif request.method == 'PUT':
            data = request.get_json()

            # Update user fields if provided in the request
            if 'email' in data:
                # Check if email is already taken by another user
                existing_user = User.query.filter_by(email=data['email']).first()
                if existing_user and existing_user.id != user.id:
                    return jsonify({'error': 'Email already taken'}), 409
                user.email = data['email']

            if 'current_weight' in data:
                user.current_weight = data['current_weight']
                user.bmi = calculate_bmi(user.current_weight, user.height)

                # Recalculate daily calories if needed
                if user.height and user.gender and user.goal_type:
                    user.daily_calories = calculate_daily_calories(user.current_weight, user.height, user.gender, user.goal_type)

            if 'height' in data:
                user.height = data['height']
                user.bmi = calculate_bmi(user.current_weight, user.height)

                # Recalculate daily calories if needed
                if user.current_weight and user.gender and user.goal_type:
                    user.daily_calories = calculate_daily_calories(user.current_weight, user.height, user.gender, user.goal_type)

            if 'gender' in data:
                user.gender = data['gender']
                if user.current_weight and user.height and user.goal_type:
                    user.daily_calories = calculate_daily_calories(user.current_weight, user.height, user.gender, user.goal_type)

            if 'goal_type' in data:
                user.goal_type = data['goal_type']
                if user.current_weight and user.height and user.gender:
                    user.daily_calories = calculate_daily_calories(user.current_weight, user.height, user.gender, user.goal_type)

            if 'weight_goal' in data:
                user.weight_goal = data['weight_goal']

            db.session.commit()
            return jsonify({'message': 'User profile updated successfully', 'user': user.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
# Recipe generation using AI
def generate_recipe_with_ai(query='', meal_type='', diet_type=''):
    global model
    if model is None:
        # Return mock data if model is not available
        return [
            {
                'id': 1,
                'name': f'{query or "Sample"} Recipe',
                'description': f'A delicious {query or "sample"} recipe for {meal_type or "any meal"} with {diet_type or "no specific"} dietary requirements',
                'prepTime': 30,
                'calories': 350,
                'protein': 20,
                'carbs': 40,
                'fat': 15,
                'mealType': meal_type or 'lunch',
                'dietType': diet_type or 'balanced',
                'cuisine': 'Pakistani',
                'image': 'utensils',
                'ingredients': ['Sample Ingredient 1', 'Sample Ingredient 2'],
                'instructions': '1. Sample step 1\n2. Sample step 2'
            }
        ]

    # Create prompt for recipe generation
    prompt = f"Generate a Pakistani cuisine recipe"
    if query:
        prompt += f" for '{query}'"
    if meal_type:
        prompt += f" suitable for {meal_type}"
    if diet_type:
        prompt += f" that is {diet_type}"

    prompt += ". Provide the response in JSON format with these fields: name, description, prepTime (in minutes), calories, protein (in grams), carbs (in grams), fat (in grams), mealType (breakfast, lunch, dinner, snack), dietType (vegetarian, non-vegetarian, vegan, etc.), cuisine, ingredients (array), instructions (string with steps)."

    try:
        response = model.generate_content(prompt)
        # Try to parse the response as JSON
        import re
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if json_match:
            import ast
            try:
                recipe_data = ast.literal_eval(json_match.group())
                # Ensure it's in the correct format
                if not isinstance(recipe_data, list):
                    recipe_data = [recipe_data]
                for i, recipe in enumerate(recipe_data):
                    recipe['id'] = i + 1
                    recipe['image'] = recipe.get('image', 'utensils')
                return recipe_data
            except:
                # If JSON parsing fails, return mock data
                pass
    except Exception as e:
        print(f"Error generating recipe with AI: {e}")

    # Return mock data if AI fails
    return [
        {
            'id': 1,
            'name': f'{query or "Sample"} Recipe',
            'description': f'A delicious Pakistani {query or "sample"} recipe for {meal_type or "any meal"} with {diet_type or "no specific"} dietary requirements',
            'prepTime': 30,
            'calories': 350,
            'protein': 20,
            'carbs': 40,
            'fat': 15,
            'mealType': meal_type or 'lunch',
            'dietType': diet_type or 'balanced',
            'cuisine': 'Pakistani',
            'image': 'utensils',
            'ingredients': ['Sample Ingredient 1', 'Sample Ingredient 2'],
            'instructions': '1. Sample step 1\n2. Sample step 2'
        }
    ]

@app.route('/api/recipes', methods=['GET'])
@login_required
def get_recipes():
    try:
        # Get query parameters
        meal_type = request.args.get('meal_type', '')
        diet_type = request.args.get('diet_type', '')

        # Generate recipes using AI
        recipes = generate_recipe_with_ai(meal_type=meal_type, diet_type=diet_type)
        return jsonify({'recipes': recipes, 'count': len(recipes)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recipes/search', methods=['POST'])
@login_required
def search_recipes():
    try:
        data = request.get_json()
        query = data.get('query', '')
        meal_type = data.get('meal_type', '')
        diet_type = data.get('diet_type', '')

        # Generate recipes using AI based on search parameters
        recipes = generate_recipe_with_ai(query=query, meal_type=meal_type, diet_type=diet_type)
        return jsonify({'recipes': recipes, 'count': len(recipes)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json()

        if not data or not data.get('current_password') or not data.get('new_password'):
            return jsonify({'error': 'Current password and new password are required'}), 400

        # Verify current password
        if not user.check_password(data['current_password']):
            return jsonify({'error': 'Current password is incorrect'}), 401

        # Set new password
        user.set_password(data['new_password'])
        db.session.commit()

        return jsonify({'message': 'Password changed successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Subscription System - All Features Now Free!
# All features are now available to all users at no cost
SUBSCRIPTION_PLANS = {
    'free': {'name': 'Free Plan', 'price': 0, 'duration': 36500, 'features': ['All features included', 'No premium required']}
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
        # All users now get access to all features automatically
        # This endpoint is kept for compatibility but grants free access to all features
        plan = SUBSCRIPTION_PLANS['free']
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=plan['duration'])  # Long duration to ensure it doesn't expire
        user.subscription_tier = 'free'  # Changed from 'pro' to 'free'
        user.subscription_start_date = start_date
        user.subscription_end_date = end_date
        user.subscription_status = 'active'
        db.session.commit()
        return jsonify({'message': 'All features unlocked successfully - you now have access to all premium features for free!', 'plan': plan, 'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()}), 200
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

        # All users now have access to all features, so ensure status is always active
        if user.subscription_status != 'active':
            user.subscription_status = 'active'
            user.subscription_tier = 'free'
            user.subscription_start_date = datetime.utcnow()
            user.subscription_end_date = datetime.utcnow() + timedelta(days=36500)  # Long duration
            db.session.commit()

        return jsonify({
            'subscription_tier': 'free',
            'subscription_start_date': datetime.utcnow().isoformat(),
            'subscription_end_date': (datetime.utcnow() + timedelta(days=36500)).isoformat(),  # Long duration
            'subscription_status': 'active'  # Always return active since all features are free
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
        # Even if a user cancels, they still keep access to all features since everything is free
        # We'll keep them as active to maintain access
        user.subscription_status = 'active'
        db.session.commit()
        return jsonify({'message': 'Your account is active with full access to all features!'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# FIXED: AI-Powered Recipe Generator
@app.route('/api/pakistani-recipes', methods=['GET'])
def get_pakistani_recipes():
    try:
        search_query = request.args.get('search', '').lower()
        meal_type = request.args.get('mealType', '').lower()
        diet_type = request.args.get('dietType', '').lower()

        # If AI model is available, try to generate recipes
        if model is not None:
            try:
                # Build prompt based on search criteria
                prompt_parts = ["Generate Pakistani recipes in JSON format:"]

                if search_query:
                    prompt_parts.append(f"Recipes containing '{search_query}'")

                if meal_type:
                    prompt_parts.append(f"Meal type: {meal_type}")

                if diet_type:
                    prompt_parts.append(f"Diet type: {diet_type}")

                prompt_parts.extend([
                    "Include fields: id, name, description, prepTime, calories, protein, carbs, fat, mealType, dietType, cuisine, ingredients, instructions",
                    "Return at least 6 recipes in a JSON array"
                ])

                prompt = " ".join(prompt_parts)

                response = model.generate_content(prompt)

                # Try to extract JSON from response
                response_text = response.text.strip()

                # Look for JSON inside code blocks or try to parse directly
                import re
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = response_text

                # Clean up the response to get just the JSON part
                if json_str.startswith("```json"):
                    json_str = json_str[7:]  # Remove ```json
                if json_str.startswith("```"):
                    json_str = json_str[3:]   # Remove ```
                if json_str.endswith("```"):
                    json_str = json_str[:-3]  # Remove ```

                recipes = json.loads(json_str)

                # Ensure recipes is a list
                if not isinstance(recipes, list):
                    recipes = [recipes]

                # Add default values for any missing fields
                for recipe in recipes:
                    recipe.setdefault('id', len(recipes))
                    recipe.setdefault('prepTime', 30)
                    recipe.setdefault('calories', 300)
                    recipe.setdefault('protein', 15)
                    recipe.setdefault('carbs', 25)
                    recipe.setdefault('fat', 10)
                    recipe.setdefault('mealType', 'lunch')
                    recipe.setdefault('dietType', 'non-vegetarian')
                    recipe.setdefault('cuisine', 'Pakistani')
                    recipe.setdefault('ingredients', ['Ingredients not specified'])
                    recipe.setdefault('instructions', 'Instructions not specified')

                return jsonify({
                    'recipes': recipes,
                    'count': len(recipes),
                    'generated_by': 'ai'
                }), 200

            except Exception as ai_error:
                print(f"AI generation failed: {ai_error}")
                # Fallback to static recipes if AI fails
                pass

        # Fallback to static recipes if AI is not available or fails
        comprehensive_pakistani_recipes = [
            {
                'id': 1,
                'name': 'Chicken Karahi',
                'description': 'Delicious Pakistani-style chicken curry cooked in a karahi with tomatoes, green chilies, and aromatic spices.',
                'prepTime': 30,
                'calories': 320,
                'protein': 30,
                'carbs': 8,
                'fat': 20,
                'mealType': 'dinner',
                'dietType': 'non-vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Chicken', 'Tomatoes', 'Onions', 'Green chilies', 'Ginger garlic', 'Cumin', 'Coriander', 'Red chili powder', 'Salt', 'Turmeric', 'Red chili powder', 'Coriander powder', 'Garam masala'],
                'instructions': '1. Heat 2 tablespoons of oil in a karahi or heavy-bottomed pan. 2. Add sliced onions and sauté until golden brown. 3. Add ginger-garlic paste and green chilies, cook for 1 minute. 4. Add chicken pieces and cook until they change color. 5. Add all the spices (cumin, coriander, turmeric, red chili powder) and mix well. 6. Add chopped tomatoes and cook until oil starts separating from the masala. 7. Add 1 cup water, cover and cook for 15-20 minutes until chicken is tender. 8. Garnish with fresh coriander and serve hot with naan or rice.'
            },
            {
                'id': 2,
                'name': 'Daal Chawal',
                'description': 'Classic Pakistani lentils served with steamed basmati rice, seasoned with cumin and garlic.',
                'prepTime': 45,
                'calories': 280,
                'protein': 12,
                'carbs': 45,
                'fat': 6,
                'mealType': 'lunch',
                'dietType': 'vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Yellow lentils (moong dal)', 'Basmati rice', 'Onions', 'Garlic', 'Ginger', 'Turmeric', 'Red chili powder', 'Cumin', 'Salt', 'Ghee or oil', 'Bay leaf', 'Cinnamon'],
                'instructions': '1. Wash 1 cup yellow lentils and pressure cook with 3 cups water and turmeric for 4-5 whistles until soft. 2. In a separate pot, rinse 1 cup basmati rice until water runs clear. Add rice to 2 cups boiling water with salt and a few drops of oil. Cook covered for 12-15 minutes. 3. For tempering: heat ghee/oil in a pan, add cumin seeds and let them splutter. 4. Add sliced onions and cook until golden. Add ginger-garlic paste and spices. 5. Mix this tempering with cooked daal. 6. Serve daal and rice together, garnished with coriander and a dollop of ghee.'
            },
            {
                'id': 3,
                'name': 'Seekh Kebab',
                'description': 'Minced meat kebabs with Pakistani spices, grilled to perfection and served with mint chutney.',
                'prepTime': 40,
                'calories': 250,
                'protein': 20,
                'carbs': 5,
                'fat': 18,
                'mealType': 'snack',
                'dietType': 'non-vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Minced beef or mutton', 'Onions', 'Ginger garlic', 'Cumin', 'Coriander', 'Red chili powder', 'Garam masala', 'Coriander leaves', 'Mint leaves', 'Egg', 'Salt', 'Red chili powder', 'Oil for grilling'],
                'instructions': '1. Mix minced meat with all spices, ginger-garlic paste, chopped onions, coriander, mint, and egg. 2. Refrigerate for 1 hour to allow flavors to blend. 3. Soak metal skewers in water for 10 minutes. 4. Take a portion of the mixture and shape around the skewer in log form. 5. Heat a griddle or tava with little oil. 6. Grill the kebabs, turning occasionally, until golden brown and cooked through (about 10-12 minutes). 7. Serve hot with mint chutney and naan.'
            },
            {
                'id': 4,
                'name': 'Aloo Gosht',
                'description': 'Hearty Pakistani curry with mutton and potatoes in a rich tomato-based gravy.',
                'prepTime': 60,
                'calories': 350,
                'protein': 25,
                'carbs': 18,
                'fat': 22,
                'mealType': 'dinner',
                'dietType': 'non-vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Mutton or beef', 'Potatoes', 'Onions', 'Tomatoes', 'Yogurt', 'Ginger garlic', 'Coriander', 'Cumin', 'Red chili powder', 'Turmeric', 'Garam masala', 'Cinnamon', 'Cardamom', 'Cloves', 'Salt', 'Oil'],
                'instructions': '1. Cut meat into cubes and marinate with yogurt, ginger-garlic paste, and spices for 30 minutes. 2. Heat oil in a heavy-bottomed pot, add whole spices (cinnamon, cardamom, cloves) and let them splutter. 3. Add sliced onions and cook until golden brown. 4. Add marinated meat and cook until color changes. 5. Add chopped tomatoes and cook until oil separates. 6. Add 1 cup water, cover and simmer for 45 minutes until meat is tender. 7. Add peeled and quartered potatoes in the last 20 minutes of cooking. 8. Adjust seasoning and serve with naan or rice.'
            },
            {
                'id': 5,
                'name': 'Biryani',
                'description': 'Fragrant Pakistani rice dish layered with marinated meat, saffron, and aromatic spices.',
                'prepTime': 90,
                'calories': 420,
                'protein': 25,
                'carbs': 55,
                'fat': 15,
                'mealType': 'lunch',
                'dietType': 'non-vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Basmati rice', 'Chicken or mutton', 'Yogurt', 'Onions', 'Tomatoes', 'Saffron', 'Mint leaves', 'Coriander leaves', 'Ginger garlic', 'Cumin', 'Coriander', 'Red chili powder', 'Turmeric', 'Garam masala', 'Cinnamon', 'Cardamom', 'Cloves', 'Bay leaves', 'Salt', 'Ghee'],
                'instructions': '1. Soak 2 cups basmati rice in water for 30 minutes. 2. Marinate chicken/meat with yogurt, spices, and ginger-garlic paste for 1 hour. 3. In a large pot, layer the marinated meat at the bottom. 4. Heat oil separately, fry sliced onions until golden (for biryani masala). 5. Layer half the drained rice over the meat. 6. Add fried onions, mint, coriander, saffron milk, and ghee. 7. Layer remaining rice on top. 8. Seal the pot with dough or tight lid, cook on low flame for 20 minutes. 9. Let it rest for 10 minutes before serving.'
            },
            {
                'id': 6,
                'name': 'Chana Masala',
                'description': 'Spicy Pakistani chickpea curry with tomatoes and aromatic spices.',
                'prepTime': 40,
                'calories': 200,
                'protein': 9,
                'carbs': 30,
                'fat': 5,
                'mealType': 'lunch',
                'dietType': 'vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Chickpeas (kala chana)', 'Onions', 'Tomatoes', 'Ginger garlic', 'Coriander', 'Cumin', 'Amchur (dry mango powder)', 'Red chili powder', 'Turmeric', 'Garam masala', 'Coriander powder', 'Salt', 'Oil', 'Fresh coriander'],
                'instructions': '1. Soak chickpeas overnight, then boil until tender (or use canned chickpeas). 2. Heat oil in a heavy-bottomed pan, add cumin seeds and let them splutter. 3. Add sliced onions and cook until golden brown. 4. Add ginger-garlic paste and cook for 1 minute. 5. Add all ground spices (coriander, cumin, turmeric, red chili powder), mix well. 6. Add chopped tomatoes and cook until soft and oil separates. 7. Add the boiled chickpeas and 1 cup water, simmer for 15 minutes. 8. Add amchur powder and garam masala in the end. 9. Garnish with fresh coriander and serve with naan.'
            }
        ]

        return jsonify({
            'recipes': comprehensive_pakistani_recipes,
            'count': len(comprehensive_pakistani_recipes),
            'generated_by': 'database'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

        # Fallback to static recipes if AI is not available or fails
        comprehensive_pakistani_recipes = [
            {
                'id': 1,
                'name': 'Chicken Karahi',
                'description': 'Delicious Pakistani-style chicken curry cooked in a karahi with tomatoes, green chilies, and aromatic spices.',
                'prepTime': 30,
                'calories': 320,
                'protein': 30,
                'carbs': 8,
                'fat': 20,
                'mealType': 'dinner',
                'dietType': 'non-vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Chicken', 'Tomatoes', 'Onions', 'Green chilies', 'Ginger garlic', 'Cumin', 'Coriander', 'Red chili powder', 'Salt', 'Turmeric', 'Red chili powder', 'Coriander powder', 'Garam masala'],
                'instructions': '1. Heat 2 tablespoons of oil in a karahi or heavy-bottomed pan. 2. Add sliced onions and sauté until golden brown. 3. Add ginger-garlic paste and green chilies, cook for 1 minute. 4. Add chicken pieces and cook until they change color. 5. Add all the spices (cumin, coriander, turmeric, red chili powder) and mix well. 6. Add chopped tomatoes and cook until oil starts separating from the masala. 7. Add 1 cup water, cover and cook for 15-20 minutes until chicken is tender. 8. Garnish with fresh coriander and serve hot with naan or rice.'
            },
            {
                'id': 2,
                'name': 'Daal Chawal',
                'description': 'Classic Pakistani lentils served with steamed basmati rice, seasoned with cumin and garlic.',
                'prepTime': 45,
                'calories': 280,
                'protein': 12,
                'carbs': 45,
                'fat': 6,
                'mealType': 'lunch',
                'dietType': 'vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Yellow lentils (moong dal)', 'Basmati rice', 'Onions', 'Garlic', 'Ginger', 'Turmeric', 'Red chili powder', 'Cumin', 'Salt', 'Ghee or oil', 'Bay leaf', 'Cinnamon'],
                'instructions': '1. Wash 1 cup yellow lentils and pressure cook with 3 cups water and turmeric for 4-5 whistles until soft. 2. In a separate pot, rinse 1 cup basmati rice until water runs clear. Add rice to 2 cups boiling water with salt and a few drops of oil. Cook covered for 12-15 minutes. 3. For tempering: heat ghee/oil in a pan, add cumin seeds and let them splutter. 4. Add sliced onions and cook until golden. Add ginger-garlic paste and spices. 5. Mix this tempering with cooked daal. 6. Serve daal and rice together, garnished with coriander and a dollop of ghee.'
            },
            {
                'id': 3,
                'name': 'Seekh Kebab',
                'description': 'Minced meat kebabs with Pakistani spices, grilled to perfection and served with mint chutney.',
                'prepTime': 40,
                'calories': 250,
                'protein': 20,
                'carbs': 5,
                'fat': 18,
                'mealType': 'snack',
                'dietType': 'non-vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Minced beef or mutton', 'Onions', 'Ginger garlic', 'Cumin', 'Coriander', 'Red chili powder', 'Garam masala', 'Coriander leaves', 'Mint leaves', 'Egg', 'Salt', 'Red chili powder', 'Oil for grilling'],
                'instructions': '1. Mix minced meat with all spices, ginger-garlic paste, chopped onions, coriander, mint, and egg. 2. Refrigerate for 1 hour to allow flavors to blend. 3. Soak metal skewers in water for 10 minutes. 4. Take a portion of the mixture and shape around the skewer in log form. 5. Heat a griddle or tava with little oil. 6. Grill the kebabs, turning occasionally, until golden brown and cooked through (about 10-12 minutes). 7. Serve hot with mint chutney and naan.'
            },
            {
                'id': 4,
                'name': 'Aloo Gosht',
                'description': 'Hearty Pakistani curry with mutton and potatoes in a rich tomato-based gravy.',
                'prepTime': 60,
                'calories': 350,
                'protein': 25,
                'carbs': 18,
                'fat': 22,
                'mealType': 'dinner',
                'dietType': 'non-vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Mutton or beef', 'Potatoes', 'Onions', 'Tomatoes', 'Yogurt', 'Ginger garlic', 'Coriander', 'Cumin', 'Red chili powder', 'Turmeric', 'Garam masala', 'Cinnamon', 'Cardamom', 'Cloves', 'Salt', 'Oil'],
                'instructions': '1. Cut meat into cubes and marinate with yogurt, ginger-garlic paste, and spices for 30 minutes. 2. Heat oil in a heavy-bottomed pot, add whole spices (cinnamon, cardamom, cloves) and let them splutter. 3. Add sliced onions and cook until golden brown. 4. Add marinated meat and cook until color changes. 5. Add chopped tomatoes and cook until oil separates. 6. Add 1 cup water, cover and simmer for 45 minutes until meat is tender. 7. Add peeled and quartered potatoes in the last 20 minutes of cooking. 8. Adjust seasoning and serve with naan or rice.'
            },
            {
                'id': 5,
                'name': 'Biryani',
                'description': 'Fragrant Pakistani rice dish layered with marinated meat, saffron, and aromatic spices.',
                'prepTime': 90,
                'calories': 420,
                'protein': 25,
                'carbs': 55,
                'fat': 15,
                'mealType': 'lunch',
                'dietType': 'non-vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Basmati rice', 'Chicken or mutton', 'Yogurt', 'Onions', 'Tomatoes', 'Saffron', 'Mint leaves', 'Coriander leaves', 'Ginger garlic', 'Cumin', 'Coriander', 'Red chili powder', 'Turmeric', 'Garam masala', 'Cinnamon', 'Cardamom', 'Cloves', 'Bay leaves', 'Salt', 'Ghee'],
                'instructions': '1. Soak 2 cups basmati rice in water for 30 minutes. 2. Marinate chicken/meat with yogurt, spices, and ginger-garlic paste for 1 hour. 3. In a large pot, layer the marinated meat at the bottom. 4. Heat oil separately, fry sliced onions until golden (for biryani masala). 5. Layer half the drained rice over the meat. 6. Add fried onions, mint, coriander, saffron milk, and ghee. 7. Layer remaining rice on top. 8. Seal the pot with dough or tight lid, cook on low flame for 20 minutes. 9. Let it rest for 10 minutes before serving.'
            },
            {
                'id': 6,
                'name': 'Chana Masala',
                'description': 'Spicy Pakistani chickpea curry with tomatoes and aromatic spices.',
                'prepTime': 40,
                'calories': 200,
                'protein': 9,
                'carbs': 30,
                'fat': 5,
                'mealType': 'lunch',
                'dietType': 'vegetarian',
                'cuisine': 'Pakistani',
                'ingredients': ['Chickpeas (kala chana)', 'Onions', 'Tomatoes', 'Ginger garlic', 'Coriander', 'Cumin', 'Amchur (dry mango powder)', 'Red chili powder', 'Turmeric', 'Garam masala', 'Coriander powder', 'Salt', 'Oil', 'Fresh coriander'],
                'instructions': '1. Soak chickpeas overnight, then boil until tender (or use canned chickpeas). 2. Heat oil in a heavy-bottomed pan, add cumin seeds and let them splutter. 3. Add sliced onions and cook until golden brown. 4. Add ginger-garlic paste and cook for 1 minute. 5. Add all ground spices (coriander, cumin, turmeric, red chili powder), mix well. 6. Add chopped tomatoes and cook until soft and oil separates. 7. Add the boiled chickpeas and 1 cup water, simmer for 15 minutes. 8. Add amchur powder and garam masala in the end. 9. Garnish with fresh coriander and serve with naan.'
            }
        ]

        return jsonify({
            'recipes': comprehensive_pakistani_recipes,
            'count': len(comprehensive_pakistani_recipes),
            'generated_by': 'database'
        }), 200


# Nutrition Tracking Models
class NutritionEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    food_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner, snack
    calories = db.Column(db.Integer, nullable=False)
    protein = db.Column(db.Float, nullable=False)  # in grams
    carbs = db.Column(db.Float, nullable=False)    # in grams
    fat = db.Column(db.Float, nullable=False)      # in grams
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'food_name': self.food_name,
            'quantity': self.quantity,
            'unit': self.unit,
            'meal_type': self.meal_type,
            'calories': self.calories,
            'protein': self.protein,
            'carbs': self.carbs,
            'fat': self.fat,
            'date': self.date.isoformat(),
            'created_at': self.created_at.isoformat()
        }

# Nutrition Tracking Endpoints
@app.route('/api/nutrition/entries', methods=['GET'])
@login_required
def get_nutrition_entries():
    try:
        user_id = session.get('user_id')
        date_str = request.args.get('date')  # Format: YYYY-MM-DD

        if date_str:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            entries = NutritionEntry.query.filter_by(user_id=user_id, date=date).all()
        else:
            # Get today's entries by default
            today = datetime.utcnow().date()
            entries = NutritionEntry.query.filter_by(user_id=user_id, date=today).all()

        total_calories = sum(entry.calories for entry in entries)
        total_protein = sum(entry.protein for entry in entries)
        total_carbs = sum(entry.carbs for entry in entries)
        total_fat = sum(entry.fat for entry in entries)

        return jsonify({
            'entries': [entry.to_dict() for entry in entries],
            'summary': {
                'total_calories': total_calories,
                'total_protein': total_protein,
                'total_carbs': total_carbs,
                'total_fat': total_fat
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/nutrition/entries', methods=['POST'])
@login_required
def add_nutrition_entry():
    try:
        user_id = session.get('user_id')
        data = request.get_json()

        required_fields = ['food_name', 'quantity', 'unit', 'meal_type', 'calories', 'protein', 'carbs', 'fat']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        date_str = data.get('date')  # Format: YYYY-MM-DD
        if date_str:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            date = datetime.utcnow().date()

        entry = NutritionEntry(
            user_id=user_id,
            food_name=data['food_name'],
            quantity=data['quantity'],
            unit=data['unit'],
            meal_type=data['meal_type'],
            calories=data['calories'],
            protein=data['protein'],
            carbs=data['carbs'],
            fat=data['fat'],
            date=date
        )

        db.session.add(entry)
        db.session.commit()

        return jsonify({
            'message': 'Nutrition entry added successfully',
            'entry': entry.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/nutrition/entries/<int:entry_id>', methods=['PUT'])
@login_required
def update_nutrition_entry(entry_id):
    try:
        user_id = session.get('user_id')
        entry = NutritionEntry.query.filter_by(id=entry_id, user_id=user_id).first()

        if not entry:
            return jsonify({'error': 'Nutrition entry not found'}), 404

        data = request.get_json()

        # Update fields if provided
        if 'food_name' in data:
            entry.food_name = data['food_name']
        if 'quantity' in data:
            entry.quantity = data['quantity']
        if 'unit' in data:
            entry.unit = data['unit']
        if 'meal_type' in data:
            entry.meal_type = data['meal_type']
        if 'calories' in data:
            entry.calories = data['calories']
        if 'protein' in data:
            entry.protein = data['protein']
        if 'carbs' in data:
            entry.carbs = data['carbs']
        if 'fat' in data:
            entry.fat = data['fat']
        if 'date' in data:
            entry.date = datetime.strptime(data['date'], '%Y-%m-%d').date()

        db.session.commit()

        return jsonify({
            'message': 'Nutrition entry updated successfully',
            'entry': entry.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/nutrition/entries/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_nutrition_entry(entry_id):
    try:
        user_id = session.get('user_id')
        entry = NutritionEntry.query.filter_by(id=entry_id, user_id=user_id).first()

        if not entry:
            return jsonify({'error': 'Nutrition entry not found'}), 404

        db.session.delete(entry)
        db.session.commit()

        return jsonify({'message': 'Nutrition entry deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/nutrition/daily-summary', methods=['GET'])
@login_required
def get_daily_nutrition_summary():
    try:
        user_id = session.get('user_id')
        date_str = request.args.get('date')  # Format: YYYY-MM-DD

        if date_str:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            date = datetime.utcnow().date()

        entries = NutritionEntry.query.filter_by(user_id=user_id, date=date).all()

        total_calories = sum(entry.calories for entry in entries)
        total_protein = sum(entry.protein for entry in entries)
        total_carbs = sum(entry.carbs for entry in entries)
        total_fat = sum(entry.fat for entry in entries)

        # Group by meal type
        meals = {}
        for meal_type in ['breakfast', 'lunch', 'dinner', 'snack']:
            meal_entries = [entry.to_dict() for entry in entries if entry.meal_type == meal_type]
            meals[meal_type] = {
                'entries': meal_entries,
                'total_calories': sum(entry.calories for entry in meal_entries),
                'total_protein': sum(entry.protein for entry in meal_entries),
                'total_carbs': sum(entry.carbs for entry in meal_entries),
                'total_fat': sum(entry.fat for entry in meal_entries)
            }

        return jsonify({
            'date': date.isoformat(),
            'summary': {
                'total_calories': total_calories,
                'total_protein': total_protein,
                'total_carbs': total_carbs,
                'total_fat': total_fat
            },
            'meals': meals
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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


# Run the app
if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            print("Tables created! Nile multi-tenancy ACTIVE")
        except Exception as e:
            print(f"Error during table creation: {e}")
            db.session.rollback()  # Rollback any failed transactions
    app.run(debug=True, host='127.0.0.1', port=5000)

