from flask import Flask, request, jsonify, render_template_string, send_from_directory, send_file, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')  # Set a secret key for sessions
CORS(app)  # Enable CORS for frontend communication

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, '..', '..', 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

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
            'daily_calories': self.daily_calories
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
        
        # Try to create a model - let's try with gemini-pro as default
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        print("Gemini model configured successfully")
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
    }
}

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

# Default route to serve the login page
@app.route('/')
def index():
    html_path = os.path.join(os.path.dirname(__file__), 'login.html')
    return send_file(html_path)

# Route to serve dashboard
@app.route('/dashboard')
def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
    return send_file(html_path)

# Route to serve chatbot interface
@app.route('/chatbot')
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

# Route to serve static files (HTML files)
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

# Run the app
def start():
    app.run(debug=True)