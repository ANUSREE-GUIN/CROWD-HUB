import os
from datetime import timedelta

from flask import Flask, request, jsonify # type: ignore
from flask_sqlalchemy import SQLAlchemy # type: ignore
from flask_bcrypt import Bcrypt # type: ignore
import flask_jwt_extended
from flask_jwt_extended import ( # type: ignore
    create_access_token,
    jwt_required,
    JWTManager,
    get_jwt_identity,
)

# --- Configuration ---
# ⭐ FINAL CONFIGURATION: Root user with a BLANK password connecting to 'user' database on 'localhost'.
DATABASE_URI = 'mysql+pymysql://root:@localhost/user' 

SECRET_KEY = os.environ.get('SECRET_KEY', 'SUPER_SECRET_AND_COMPLEX_KEY') 

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = SECRET_KEY
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['SECRET_KEY'] = SECRET_KEY 

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# --- Database Model ---
class User(db.Model):
    """User data model."""
    # SQLAlchemy defaults the table name to the lowercase version of the class name: 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False) 

    def set_password(self, password):
        """Hashes the password using Bcrypt."""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Checks if the provided password matches the stored hash."""
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# Create tables *after* defining models (call this once)
with app.app_context():
    try:
        db.create_all()
        print("Database connection successful and 'user' table checked/created.")
    except Exception as e:
        # This will fail if MySQL is not running or the 'user' database doesn't exist.
        print(f"ERROR: Failed to connect to MySQL/MariaDB. Ensure XAMPP/MAMP is running and the 'user' database exists. Error: {e}")

# --- API Routes ---

@app.route('/register', methods=['POST'])
def register():
    """Endpoint for user registration."""
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify({"msg": "Missing username, email, or password"}), 400

    if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
        return jsonify({"msg": "User or email already exists"}), 409

    new_user = User(username=username, email=email)
    new_user.set_password(password)

    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"msg": "User registered successfully"}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Database error during registration: {e}") 
        return jsonify({"msg": "An error occurred during registration", "error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    """Endpoint for user login and JWT generation."""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not all([username, password]):
        return jsonify({"msg": "Missing username or password"}), 400

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        # Create a new access token for the user
        access_token = create_access_token(identity=user.id)
        return jsonify(access_token=access_token), 200
    else:
        return jsonify({"msg": "Bad username or password"}), 401

@app.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    """A route that requires a valid JWT access token."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if user:
        return jsonify(logged_in_as=user.username, user_id=user.id, message="Access granted to protected endpoint"), 200
    return jsonify({"msg": "User not found in database"}), 404

# --- Main Run Block ---
if __name__ == '__main__':
    # Ensure you have installed PyMySQL: pip install PyMySQL
    app.run(debug=True)
