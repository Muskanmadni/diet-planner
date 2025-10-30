import requests
import json

# Base URL for the Flask app (make sure it's running on localhost:5000)
BASE_URL = 'http://127.0.0.1:5000'

def test_registration():
    print("Testing registration endpoint...")
    
    # Prepare registration data
    registration_data = {
        "email": "test@example.com",
        "password": "testpassword123",
        "current_weight": 70.0,
        "height": 175.0,
        "gender": "male",
        "goal_type": "lose",
        "weight_goal": 65.0
    }
    
    try:
        # Make the registration request
        response = requests.post(
            f'{BASE_URL}/api/register',
            headers={'Content-Type': 'application/json'},
            data=json.dumps(registration_data)
        )
        
        print(f"Registration response status: {response.status_code}")
        print(f"Registration response: {response.json()}")
        
        if response.status_code == 201:
            print("Registration successful!")
            return True
        else:
            print("Registration failed!")
            return False
            
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the server. Make sure the Flask app is running on http://127.0.0.1:5000")
        return False
    except Exception as e:
        print(f"Error during registration test: {e}")
        return False

def test_login():
    print("\nTesting login endpoint...")
    
    # Prepare login data
    login_data = {
        "email": "test@example.com",
        "password": "testpassword123"
    }
    
    try:
        # Make the login request
        response = requests.post(
            f'{BASE_URL}/api/login',
            headers={'Content-Type': 'application/json'},
            data=json.dumps(login_data)
        )
        
        print(f"Login response status: {response.status_code}")
        print(f"Login response: {response.json()}")
        
        if response.status_code == 200:
            print("Login successful!")
            return True
        else:
            print("Login failed!")
            return False
            
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the server. Make sure the Flask app is running on http://127.0.0.1:5000")
        return False
    except Exception as e:
        print(f"Error during login test: {e}")
        return False

if __name__ == "__main__":
    # Test registration first
    registration_success = test_registration()
    
    if registration_success:
        # Then test login
        test_login()