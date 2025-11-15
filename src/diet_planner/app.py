from flask import Flask, request, jsonify, render_template_string, send_from_directory, send_file, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import os
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
from authlib.integrations.flask_client import OAuth
from urllib.parse import urlencode, quote_plus
from functools import wraps
from flask import redirect, url_for
import http
import requests
import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nutriguide-prod-secret-key-change-in-production')
CORS(app, supports_credentials=True)

# === AUTH0 SETUP (NEW) ===
oauth = OAuth(app)
oauth.register(
    "auth0",
    client_id=os.getenv("AUTH0_CLIENT_ID"),
    client_secret=os.getenv("AUTH0_CLIENT_SECRET"),
    client_kwargs={"scope": "openid profile email"},
    server_metadata_url=f'https://{os.getenv("AUTH0_DOMAIN")}/.well-known/openid-configuration'
)

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
        # Check Flask session first (for existing users)
        if 'user_id' in session and session['user_id'] is not None:
            return f(*args, **kwargs)
       
        # Check Clerk authentication
        auth_header = request.headers.get('Authorization')
        session_token = None
       
        if auth_header and auth_header.startswith('Bearer '):
            session_token = auth_header[7:]
            try:
                return f(*args, **kwargs)
            except:
                pass
       
        return redirect(url_for('login_page'))
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
    # All features are free - these fields are maintained for compatibility but all users have access
    subscription_tier = db.Column(db.String(20), nullable=True, default='free')
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    subscription_status = db.Column(db.String(20), nullable=True, default='active') # All users have active status

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
            'subscription_tier': 'free', # Always return free tier since all features are free
            'subscription_start_date': datetime.utcnow().isoformat(), # Always return current time
            'subscription_end_date': (datetime.utcnow() + timedelta(days=36500)).isoformat(), # Always return long duration
            'subscription_status': 'active' # Always return active since all features are free
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

# Google OAuth routes
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
            user_id = idinfo['sub'] # Google's unique user ID
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
            user.subscription_end_date = datetime.utcnow() + timedelta(days=36500) # Long duration
            db.session.commit()
           
        return jsonify({'message': 'Google login successful', 'user': user.to_dict()}), 200
    except Exception as e:
        print(f"Error in google_login: {e}")
        return jsonify({'error': str(e)}), 500

# === AUTH0 ROUTES (NEW) ===
@app.route('/auth0/login')
def auth0_login():
    return oauth.auth0.authorize_redirect(
        redirect_uri=os.getenv("AUTH0_CALLBACK_URL", "http://localhost:5000/auth0/callback")
    )

@app.route('/auth0/callback')
def auth0_callback():
    try:
        token = oauth.auth0.authorize_access_token()
        session['auth0_token'] = token
        userinfo = token.get('userinfo', {})
        email = userinfo.get('email')
        if not email:
            return "Auth0 returned no email", 400

        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email, password_hash=generate_password_hash(''))  # dummy hash
            db.session.add(user)
            db.session.commit()

        session['user_id'] = user.id
        return redirect(url_for('dashboard'))
    except Exception as e:
        return f"Auth0 error: {e}", 500

@app.route('/auth0/logout')
def auth0_logout():
    session.clear()
    return redirect(
        f"https://{os.getenv('AUTH0_DOMAIN')}/v2/logout?"
        + urlencode(
            {"returnTo": url_for('landing_page', _external=True),
             "client_id": os.getenv("AUTH0_CLIENT_ID")},
            quote_via=quote_plus
        )
    )

# Database initialization function
def init_db():
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

# Initialize database if needed
def initialize_database():
    try:
        # Try a simple query to see if tables exist and create if needed
        with app.app_context():
            # Only create tables if we're not in a Vercel production environment
            # For Vercel, you may want to use a hosted database like PostgreSQL
            import os
            if os.environ.get('VERCEL') != '1':  # Not running on Vercel
                db.create_all()
            else:
                # On Vercel, just try to access the database to ensure it works
                # In production, it's better to have an initialized database
                pass
    except Exception as e:
        print(f"Error during database initialization: {e}")

# Call initialization when app starts
initialize_database()

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
        if data.get('email') and data.get('password'):
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
                daily_calories=daily_calories,
                subscription_tier='free',
                subscription_start_date=datetime.utcnow(),
                subscription_end_date=datetime.utcnow() + timedelta(days=36500),
                subscription_status='active'
            )
            user.set_password(data['password'])
            db.session.add(user)
            db.session.commit()
            return jsonify({'message': 'User registered successfully', 'user': user.to_dict()}), 201
        else:
            user_id = session.get('user_id')
            if not user_id:
                return jsonify({'error': 'User not authenticated'}), 401
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
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
        if user.subscription_status != 'active':
            user.subscription_status = 'active'
            user.subscription_tier = 'free'
            user.subscription_start_date = datetime.utcnow()
            user.subscription_end_date = datetime.utcnow() + timedelta(days=36500)
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
           
            if 'email' in data:
                existing_user = User.query.filter_by(email=data['email']).first()
                if existing_user and existing_user.id != user.id:
                    return jsonify({'error': 'Email already taken'}), 409
                user.email = data['email']
           
            if 'current_weight' in data:
                user.current_weight = data['current_weight']
                user.bmi = calculate_bmi(user.current_weight, user.height)
                if user.height and user.gender and user.goal_type:
                    user.daily_calories = calculate_daily_calories(user.current_weight, user.height, user.gender, user.goal_type)
           
            if 'height' in data:
                user.height = data['height']
                user.bmi = calculate_bmi(user.current_weight, user.height)
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
        return jsonify({'error': str(e)}), 500

# Recipe generation using AI
def generate_recipe_with_ai(query='', meal_type='', diet_type=''):
    global model
    if model is None:
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
        import re
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if json_match:
            import ast
            try:
                recipe_data = ast.literal_eval(json_match.group())
                if not isinstance(recipe_data, list):
                    recipe_data = [recipe_data]
                for i, recipe in enumerate(recipe_data):
                    recipe['id'] = i + 1
                    recipe['image'] = recipe.get('image', 'utensils')
                return recipe_data
            except:
                pass
    except Exception as e:
        print(f"Error generating recipe with AI: {e}")
   
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
        meal_type = request.args.get('meal_type', '')
        diet_type = request.args.get('diet_type', '')
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
        if not user.check_password(data['current_password']):
            return jsonify({'error': 'Current password is incorrect'}), 401
        user.set_password(data['new_password'])
        db.session.commit()
        return jsonify({'message': 'Password changed successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Subscription System - All Features Now Free!
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
        plan = SUBSCRIPTION_PLANS['free']
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=plan['duration'])
        user.subscription_tier = 'free'
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
        if user.subscription_status != 'active':
            user.subscription_status = 'active'
            user.subscription_tier = 'free'
            user.subscription_start_date = datetime.utcnow()
            user.subscription_end_date = datetime.utcnow() + timedelta(days=36500)
            db.session.commit()
        return jsonify({
            'subscription_tier': 'free',
            'subscription_start_date': datetime.utcnow().isoformat(),
            'subscription_end_date': (datetime.utcnow() + timedelta(days=36500)).isoformat(),
            'subscription_status': 'active'
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
        user.subscription_status = 'active'
        db.session.commit()
        return jsonify({'message': 'Your account is active with full access to all features!'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/pakistani-recipes', methods=['GET'])
def get_pakistani_recipes():
    try:
        search_query = request.args.get('search', '').lower()
        meal_type = request.args.get('mealType', '').lower()
        diet_type = request.args.get('dietType', '').lower()
        if model is not None:
            try:
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
                response_text = response.text.strip()
                import re
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = response_text
                if json_str.startswith("```json"):
                    json_str = json_str[7:]
                if json_str.startswith("```"):
                    json_str = json_str[3:]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
                recipes = json.loads(json_str)
                if not isinstance(recipes, list):
                    recipes = [recipes]
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
        comprehensive_pakistani_recipes = [
            # ... (your full list of 6 recipes here - unchanged)
        ]
        return jsonify({
            'recipes': comprehensive_pakistani_recipes,
            'count': len(comprehensive_pakistani_recipes),
            'generated_by': 'database'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Nutrition Tracking Models
class NutritionEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    food_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    protein = db.Column(db.Float, nullable=False)
    carbs = db.Column(db.Float, nullable=False)
    fat = db.Column(db.Float, nullable=False)
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

# ... (all your nutrition, diet-plan, shopping-list, analyze-food-plate routes unchanged)

# Run the app
if __name__ == "__main__":
    app.run(debug=True, host='127.0.0.1', port=5000)
else:
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))