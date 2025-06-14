import os
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from geopy.distance import geodesic
import logging
import uuid
import shortuuid

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Email configuration
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USER = os.environ.get("EMAIL_USER", "your-email@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "your-app-password")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "P2P Rental <your-email@gmail.com>")

# Define the payment service URLs
PAYMENT_API_URL = os.environ.get('PAYMENT_API_URL', 'http://localhost:5002')
VERIFICATION_SERVICE_URL = os.environ.get('PAYMENT_SERVICE_URL', 'http://localhost:5001')


# Vision API configuration
VISION_API_KEY = os.environ.get("VISION_API_KEY", "da4301423fe4439b9eb4619d88c62828")
VISION_API_URL = "https://invoiceinfomatchingopenai.openai.azure.com/"

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=["https://www.lalushbella.com"],supports_credentials=True)
# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://accessor:12345678@localhost/p2p'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models
# New OTP Session model
class OTPSession(db.Model):
    __tablename__ = 'otp_sessions'
    session_id = db.Column(db.String(36), primary_key=True)
    mobile_number = db.Column(db.String(15), nullable=False)
    email = db.Column(db.String(255))
    otp_code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    verified = db.Column(db.Boolean, default=False)
    verification_attempts = db.Column(db.Integer, default=0)
    action_type = db.Column(db.Enum('login', 'register'), nullable=False)


class User(db.Model):
    __tablename__ = 'users'
    customer_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mobile_number = db.Column(db.String(15), unique=True, nullable=False)
    name = db.Column(db.String(255))
    email = db.Column(db.String(255), unique=True)
    addresses = db.Column(db.JSON)  # Multiple addresses with pincodes
    kyc_status = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Listing(db.Model):
    __tablename__ = 'listings'
    listing_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.customer_id'), nullable=False)
    product_type = db.Column(db.Enum('AC', 'TV', 'Refrigerator', 'Microwave', 'Bed', 'Sofa', 'Table', 'Chair', 'PlayStation'), nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    invoice_value = db.Column(db.Numeric(10, 2), nullable=False)
    brand = db.Column(db.String(100), nullable=False)
    model_name = db.Column(db.String(100))
    images = db.Column(db.JSON)
    location_pincode = db.Column(db.String(10), nullable=False)
    status = db.Column(db.Enum('Active', 'Draft', 'Inactive'))
    length_cm = db.Column(db.Numeric(10, 2), nullable=False)
    width_cm = db.Column(db.Numeric(10, 2), nullable=False)
    height_cm = db.Column(db.Numeric(10, 2), nullable=False)
    weight_kg = db.Column(db.Numeric(10, 2), default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationship to User
    lender = db.relationship('User', backref='listings')

class Order(db.Model):
    __tablename__ = 'orders'
    order_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.listing_id'), nullable=False)
    borrower_id = db.Column(db.Integer, db.ForeignKey('users.customer_id'), nullable=False)
    status = db.Column(db.Enum('Confirmed', 'Payment Made', 'KYC Done', 'Awaiting Logistics', 'Delivered'))
    rental_price_per_month = db.Column(db.Numeric(10, 2))
    total_rental_price = db.Column(db.Numeric(10, 2))
    platform_fee = db.Column(db.Numeric(10, 2))
    logistics_fee = db.Column(db.Numeric(10, 2))
    ancillary_service_fee = db.Column(db.Numeric(10, 2))
    tax = db.Column(db.Numeric(10, 2))
    kyc_completed_at = db.Column(db.DateTime)
    kyc_status = db.Column(db.Boolean, default=False)
    payment_datetime = db.Column(db.DateTime)
    logistic_slot = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationships
    listing = db.relationship('Listing', backref='orders')
    borrower = db.relationship('User', foreign_keys=[borrower_id], backref='borrowed_orders')

class PincodeMaster(db.Model):
    __tablename__ = 'pincode_master'
    pincode = db.Column(db.String(10), primary_key=True)
    latitude = db.Column(db.Numeric(10, 6), nullable=False)
    longitude = db.Column(db.Numeric(10, 6), nullable=False)
    district = db.Column(db.String(100))
    state_name = db.Column(db.String(100))

class DeliverySlot(db.Model):
    __tablename__ = 'delivery_slots'
    slot_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), unique=True)
    slot_datetime = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Enum('Scheduled', 'Completed', 'Cancelled'), default='Scheduled')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationship
    order = db.relationship('Order', backref='delivery_slot')

class Logistics(db.Model):
    __tablename__ = 'logistics'
    logistics_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=False)
    transporter_details = db.Column(db.JSON)
    pickup_date = db.Column(db.Date)
    delivery_date = db.Column(db.Date)
    status = db.Column(db.Enum('Scheduled', 'In Transit', 'Delivered'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationship
    order = db.relationship('Order', backref='logistics')

# Helper Functions

# Helper functions for existing routes
def listing_to_dict(listing):
    """Convert a listing object to a dictionary"""
    # Implementation remains the same...
    pass

def order_to_dict(order):
    """Convert an order object to a dictionary"""
    # Implementation remains the same...
    pass

def calculate_distance_from_pincodes(pincode1, pincode2):
    """Calculate distance between two pincodes"""
    # Implementation remains the same...
    pass

def calculate_logistics_cost_from_distance(distance, length, width, height, weight):
    """Calculate logistics cost based on distance and dimensions"""
    # Implementation remains the same...
    pass

def analyze_image(image_url):
    """Analyze image using Vision API"""
    # Implementation remains the same...
    pass

def calculate_rent(invoice_value, purchase_date, condition_details=None):
    """Calculate rent based on invoice value, age, and condition"""
    # Implementation remains the same...
    pass

def analyze_image(image_url):
    """
    Analyze the image to determine the condition of the appliance/furniture
    and return a condition score (0.0 to 1.0) and estimated depreciation factor.
    """
    try:
        # Download the image from the URL
        response = requests.get(image_url)
        if response.status_code != 200:
            logging.error(f"Failed to download image from {image_url}")
            return {"condition_score": 0.5, "depreciation_factor": 0.2}
        
        image = Image.open(io.BytesIO(response.content))
        
        # Convert image to base64 for API request
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        # Prepare prompt for vision API
        prompt = """
        Analyze this image of furniture/appliance and determine:
        1. The overall condition (excellent, good, fair, poor)
        2. Any visible damage, wear and tear, or signs of age
        3. Estimated remaining useful life as a percentage
        4. Cleanliness and maintenance level
        5. Modern appeal and market demand for this item
        Based on these factors, provide a condition score from 0.0 (very poor) to 1.0 (like new)
        and a recommended depreciation factor from 0.0 (no additional depreciation) to 0.5 (significant depreciation).
        """
        
        # Make request to vision API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {VISION_API_KEY}"
        }
        
        payload = {
            "image": img_str,
            "prompt": prompt
        }
        
        ai_response = requests.post(
            VISION_API_URL,
            headers=headers,
            json=payload
        )
        
        if ai_response.status_code != 200:
            logging.error(f"Vision API error: {ai_response.text}")
            return {"condition_score": 0.5, "depreciation_factor": 0.2}
        
        # Parse the AI response to extract condition score and depreciation factor
        # This will depend on the exact format of your vision API's response
        result = ai_response.json()
        
        # Extract the condition score and depreciation factor from the AI response
        # This is a simplified example - adapt to your actual AI response format
        condition_score = result.get("condition_score", 0.5)
        depreciation_factor = result.get("depreciation_factor", 0.2)
        
        return {
            "condition_score": condition_score,
            "depreciation_factor": depreciation_factor
        }
    
    except Exception as e:
        logging.error(f"Error analyzing image: {str(e)}")
        # Return default values if analysis fails
        return {"condition_score": 0.5, "depreciation_factor": 0.2}

def calculate_rent(invoice_value: float, purchase_date: str, condition_details: dict = None):
    """
    Calculate the suggested monthly rental price based on:
    - Invoice value
    - Age of the item (purchase date)
    - Condition details from AI analysis (if available)
    """
    purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d")
    current_date = datetime.today()
    age_in_months = (current_date.year - purchase_date.year) * 12 + current_date.month - purchase_date.month
    
    # Base rent calculation (1/24th of invoice value)
    base_rent = invoice_value / 24
    
    # Standard age-based depreciation (0.5% per month)
    depreciation_percentage = 0.5 / 100  # 0.5% per month
    age_depreciation_value = base_rent * depreciation_percentage * age_in_months
    rent_after_age_depreciation = base_rent - age_depreciation_value
    
    # Apply AI-based condition depreciation if available
    if condition_details:
        condition_score = condition_details.get("condition_score", 0.5)
        depreciation_factor = condition_details.get("depreciation_factor", 0.2)
        
        # Adjust depreciation based on condition
        # We use condition_score to determine how much of the depreciation_factor to apply
        condition_adjustment = 1 - (depreciation_factor * (1 - condition_score))
        rent_after_condition = rent_after_age_depreciation * condition_adjustment
    else:
        # Without AI analysis, default to 20% reduction
        rent_after_condition = rent_after_age_depreciation * 0.8
    
    # Ensure rent doesn't fall below 3% of the invoice value
    min_rent = invoice_value * 0.03
    final_rent = max(rent_after_condition, min_rent)
    
    return round(final_rent, 2)

def calculate_distance_from_pincodes(pincode1, pincode2):
    """Calculate distance between two pincodes using geodesic formula"""
    loc1 = PincodeMaster.query.filter_by(pincode=pincode1).first()
    loc2 = PincodeMaster.query.filter_by(pincode=pincode2).first()
    
    if not loc1 or not loc2:
        return None
    
    return geodesic(
        (float(loc1.latitude), float(loc1.longitude)),
        (float(loc2.latitude), float(loc2.longitude))
    ).km

def calculate_logistics_cost_from_distance(distance, length_cm, width_cm, height_cm, weight_kg):
    """Calculate logistics cost based on distance and item dimensions"""
    base_fare = 200  # Base fare for first 5 KM
    
    # Additional cost for oversized items
    is_oversized = length_cm > 100 or width_cm > 50 or height_cm > 50
    cost_per_km = 45 + (5 if is_oversized else 0)
    
    # Additional cost for heavy items
    extra_weight_charge = 2 if weight_kg > 200 else 0
    
    # Calculate total cost
    additional_distance = max(0, distance - 5)  # Distance beyond first 5 KM
    logistics_cost = base_fare + additional_distance * (cost_per_km + extra_weight_charge)
    
    return round(logistics_cost, 2)

def listing_to_dict(listing):
    """Convert listing object to dictionary with lender info"""
    return {
        'listing_id': listing.listing_id,
        'product_type': listing.product_type,
        'brand': listing.brand,
        'model_name': listing.model_name,
        'purchase_date': listing.purchase_date.strftime('%Y-%m-%d') if listing.purchase_date else None,
        'invoice_value': float(listing.invoice_value) if listing.invoice_value else None,
        'location_pincode': listing.location_pincode,
        'status': listing.status,
        'dimensions': {
            'length_cm': float(listing.length_cm),
            'width_cm': float(listing.width_cm),
            'height_cm': float(listing.height_cm),
            'weight_kg': float(listing.weight_kg)
        },
        'images': listing.images,
        'created_at': listing.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'lender': {
            'customer_id': listing.lender.customer_id,
            'name': listing.lender.name
        }
    }

def order_to_dict(order):
    """Convert order object to dictionary with listing and user info"""
    listing = order.listing
    borrower = order.borrower
    
    result = {
        'order_id': order.order_id,
        'status': order.status,
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'pricing': {
            'rental_price_per_month': float(order.rental_price_per_month) if order.rental_price_per_month else None,
            'total_rental_price': float(order.total_rental_price) if order.total_rental_price else None,
            'platform_fee': float(order.platform_fee) if order.platform_fee else None,
            'logistics_fee': float(order.logistics_fee) if order.logistics_fee else None,
            'ancillary_service_fee': float(order.ancillary_service_fee) if order.ancillary_service_fee else None,
            'tax': float(order.tax) if order.tax else None
        },
        'kyc_status': order.kyc_status,
        'kyc_completed_at': order.kyc_completed_at.strftime('%Y-%m-%d %H:%M:%S') if order.kyc_completed_at else None,
        'payment_datetime': order.payment_datetime.strftime('%Y-%m-%d %H:%M:%S') if order.payment_datetime else None,
        'logistic_slot': order.logistic_slot.strftime('%Y-%m-%d %H:%M:%S') if order.logistic_slot else None,
        'listing': {
            'listing_id': listing.listing_id,
            'product_type': listing.product_type,
            'brand': listing.brand,
            'model_name': listing.model_name,
            'location_pincode': listing.location_pincode
        },
        'borrower': {
            'customer_id': borrower.customer_id,
            'name': borrower.name
        },
        'lender': {
            'customer_id': listing.lender.customer_id,
            'name': listing.lender.name
        }
    }
    
    # Add delivery slot info if available
    if hasattr(order, 'delivery_slot') and order.delivery_slot:
        slot = order.delivery_slot[0] if isinstance(order.delivery_slot, list) and order.delivery_slot else order.delivery_slot
        result['delivery_slot'] = {
            'slot_id': slot.slot_id,
            'slot_datetime': slot.slot_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            'status': slot.status
        }
    
    return result
# Routes

# Utility Functions
def generate_otp(length=6):
    """Generate a random numeric OTP of specified length"""
    return ''.join(random.choices(string.digits, k=length))

def send_email_otp(email, otp, action_type):
    """Send OTP via email"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = email
        
        if action_type == 'login':
            msg['Subject'] = "Your Login OTP for P2P Rental"
            body = f"""
            <html>
            <body>
                <h2>P2P Rental Login Verification</h2>
                <p>Your one-time password (OTP) for login is: <strong>{otp}</strong></p>
                <p>This OTP will expire in 10 minutes.</p>
                <p>If you did not request this login, please ignore this email.</p>
            </body>
            </html>
            """
        else:  # register
            msg['Subject'] = "Complete Your Registration for P2P Rental"
            body = f"""
            <html>
            <body>
                <h2>Welcome to P2P Rental!</h2>
                <p>Your one-time password (OTP) for registration is: <strong>{otp}</strong></p>
                <p>This OTP will expire in 10 minutes.</p>
                <p>If you did not attempt to register, please ignore this email.</p>
            </body>
            </html>
            """
        
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email OTP sent successfully to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False

def send_sms_otp(mobile_number, otp, action_type):
    """
    Send OTP via SMS (placeholder function)
    In production, integrate with an SMS provider like Twilio, MessageBird, etc.
    """
    action = "login to" if action_type == "login" else "register for"
    message = f"Your OTP to {action} P2P Rental is: {otp}. Valid for 10 minutes."
    
    # Placeholder for actual SMS sending
    logger.info(f"SMS would be sent to {mobile_number}: {message}")
    
    # Return True to simulate successful sending
    # In production, return actual success/failure from SMS provider
    return True

# Updated Routes for OTP Authentication

# 1. Request OTP for Login
@app.route('/login', methods=['POST'])
def login_user():
    """Request OTP for user login"""
    try:
        data = request.json
        
        if 'mobile_number' not in data:
            return jsonify({'error': 'Mobile number is required'}), 400
            
        mobile_number = data['mobile_number']
        
        # Check if user exists
        user = User.query.filter_by(mobile_number=mobile_number).first()
        
        # Generate a unique session ID
        session_id = str(uuid.uuid4())
        
        # Generate OTP
        otp_code = generate_otp()
        
        # Set expiration time (10 minutes from now)
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        if user:
            # User exists - create OTP session for login
            otp_session = OTPSession(
                session_id=session_id,
                mobile_number=mobile_number,
                email=user.email,
                otp_code=otp_code,
                expires_at=expires_at,
                action_type='login'
            )
            
            # Send OTP via email if available
            email_sent = False
            if user.email:
                email_sent = send_email_otp(user.email, otp_code, 'login')
            
            # Send OTP via SMS (you'll need to implement this with an SMS provider)
            sms_sent = send_sms_otp(mobile_number, otp_code, 'login')
            
            db.session.add(otp_session)
            db.session.commit()
            
            logger.info(f"Login OTP generated for user with mobile: {mobile_number}")
            
            return jsonify({
                'message': 'OTP sent successfully',
                'session_id': session_id,
                'is_new_user': False,
                'delivery_methods': {
                    'email': email_sent,
                    'sms': sms_sent
                }
            }), 200
        else:
            # User doesn't exist - ask to register instead
            return jsonify({
                'message': 'User not found. Please register first.',
                'is_new_user': True
            }), 404
            
    except Exception as e:
        logger.error(f"Error in login_user: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 2. Request OTP for Registration
@app.route('/register', methods=['POST'])
def register_user():
    """Request OTP for user registration"""
    try:
        data = request.json
        
        if 'mobile_number' not in data:
            return jsonify({'error': 'Mobile number is required'}), 400
            
        if 'email' not in data:
            return jsonify({'error': 'Email is required for registration'}), 400
        
        mobile_number = data['mobile_number']
        email = data['email']
        
        # Check if user already exists
        existing_user = User.query.filter_by(mobile_number=mobile_number).first()
        if existing_user:
            return jsonify({
                'message': 'User already exists. Please login instead.',
                'customer_id': existing_user.customer_id
            }), 400
        
        # Check if email is already used
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return jsonify({
                'error': 'Email is already registered with another account.'
            }), 400
        
        # Generate a unique session ID
        session_id = str(uuid.uuid4())
        
        # Generate OTP
        otp_code = generate_otp()
        
        # Set expiration time (10 minutes from now)
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        # Create OTP session for registration
        otp_session = OTPSession(
            session_id=session_id,
            mobile_number=mobile_number,
            email=email,
            otp_code=otp_code,
            expires_at=expires_at,
            action_type='register'
        )
        
        # Send OTP via email
        email_sent = send_email_otp(email, otp_code, 'register')
        
        # Send OTP via SMS
        sms_sent = send_sms_otp(mobile_number, otp_code, 'register')
        
        db.session.add(otp_session)
        db.session.commit()
        
        logger.info(f"Registration OTP generated for mobile: {mobile_number}")
        
        return jsonify({
            'message': 'OTP sent successfully',
            'session_id': session_id,
            'is_new_user': True,
            'delivery_methods': {
                'email': email_sent,
                'sms': sms_sent
            }
        }), 201
    except Exception as e:
        logger.error(f"Error in register_user: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 3. Verify OTP for Login
@app.route('/verify_login_otp', methods=['POST'])
def verify_login_otp():
    """Verify OTP for user login"""
    try:
        data = request.json
        
        if 'session_id' not in data or 'otp' not in data:
            return jsonify({'error': 'Session ID and OTP are required'}), 400
            
        session_id = data['session_id']
        otp = data['otp']
        
        # Get OTP session
        otp_session = OTPSession.query.filter_by(session_id=session_id).first()
        if not otp_session:
            return jsonify({'error': 'Invalid session ID'}), 404
        
        # Check if session is expired
        if datetime.utcnow() > otp_session.expires_at:
            return jsonify({'error': 'OTP has expired. Please request a new one.'}), 401
        
        # Check if session was for login
        if otp_session.action_type != 'login':
            return jsonify({'error': 'Invalid session type'}), 400
        
        # Check if OTP is already verified
        if otp_session.verified:
            return jsonify({'error': 'OTP already verified'}), 400
        
        # Increment verification attempts
        otp_session.verification_attempts += 1
        
        # Check if too many attempts (max 3)
        if otp_session.verification_attempts > 3:
            db.session.commit()
            return jsonify({'error': 'Too many verification attempts. Please request a new OTP.'}), 401
        
        # Verify OTP
        if otp_session.otp_code != otp:
            db.session.commit()
            return jsonify({'error': 'Invalid OTP'}), 401
        
        # Mark session as verified
        otp_session.verified = True
        db.session.commit()
        
        # Get user data
        user = User.query.filter_by(mobile_number=otp_session.mobile_number).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'message': 'Login successful',
            'customer_id': user.customer_id,
            'name': user.name,
            'email': user.email,
            'kyc_status': user.kyc_status
        }), 200
    except Exception as e:
        logger.error(f"Error in verify_login_otp: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 4. Verify OTP for Registration and Complete Registration
@app.route('/verify_register_otp', methods=['POST'])
def verify_register_otp():
    """Verify OTP and complete user registration"""
    try:
        data = request.json
        
        if 'session_id' not in data or 'otp' not in data:
            return jsonify({'error': 'Session ID and OTP are required'}), 400
            
        session_id = data['session_id']
        otp = data['otp']
        
        # Get OTP session
        otp_session = OTPSession.query.filter_by(session_id=session_id).first()
        if not otp_session:
            return jsonify({'error': 'Invalid session ID'}), 404
        
        # Check if session is expired
        if datetime.utcnow() > otp_session.expires_at:
            return jsonify({'error': 'OTP has expired. Please request a new one.'}), 401
        
        # Check if session was for registration
        if otp_session.action_type != 'register':
            return jsonify({'error': 'Invalid session type'}), 400
        
        # Check if OTP is already verified
        if otp_session.verified:
            return jsonify({'error': 'OTP already verified'}), 400
        
        # Increment verification attempts
        otp_session.verification_attempts += 1
        
        # Check if too many attempts (max 3)
        if otp_session.verification_attempts > 3:
            db.session.commit()
            return jsonify({'error': 'Too many verification attempts. Please request a new OTP.'}), 401
        
        # Verify OTP
        if otp_session.otp_code != otp:
            db.session.commit()
            return jsonify({'error': 'Invalid OTP'}), 401
        
        # Mark session as verified
        otp_session.verified = True
        
        # Get additional registration data
        name = data.get('name', '')
        addresses = data.get('addresses', {})
        
        # Create new user
        new_user = User(
            mobile_number=otp_session.mobile_number,
            name=name,
            email=otp_session.email,
            addresses=addresses,
            kyc_status=False
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        logger.info(f"New user registered with mobile: {otp_session.mobile_number}")
        
        return jsonify({
            'message': 'Registration successful',
            'customer_id': new_user.customer_id,
            'name': new_user.name,
            'email': new_user.email,
            'kyc_status': new_user.kyc_status
        }), 201
    except Exception as e:
        logger.error(f"Error in verify_register_otp: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 5. Resend OTP
@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    """Resend OTP for an existing session"""
    try:
        data = request.json
        
        if 'session_id' not in data:
            return jsonify({'error': 'Session ID is required'}), 400
            
        session_id = data['session_id']
        
        # Get OTP session
        otp_session = OTPSession.query.filter_by(session_id=session_id).first()
        if not otp_session:
            return jsonify({'error': 'Invalid session ID'}), 404
        
        # Check if session is already verified
        if otp_session.verified:
            return jsonify({'error': 'OTP already verified'}), 400
        
        # Generate new OTP
        new_otp = generate_otp()
        
        # Reset expiration time (10 minutes from now)
        otp_session.expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        # Update OTP
        otp_session.otp_code = new_otp
        
        # Reset verification attempts
        otp_session.verification_attempts = 0
        
        # Send OTP via email if available
        email_sent = False
        if otp_session.email:
            email_sent = send_email_otp(otp_session.email, new_otp, otp_session.action_type)
        
        # Send OTP via SMS
        sms_sent = send_sms_otp(otp_session.mobile_number, new_otp, otp_session.action_type)
        
        db.session.commit()
        
        logger.info(f"OTP resent for session: {session_id}")
        
        return jsonify({
            'message': 'OTP resent successfully',
            'session_id': session_id,
            'delivery_methods': {
                'email': email_sent,
                'sms': sms_sent
            }
        }), 200
    except Exception as e:
        logger.error(f"Error in resend_otp: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Existing routes remain unchanged...


@app.route('/users/<int:customer_id>', methods=['GET'])
def get_user(customer_id):
    """Get user details"""
    try:
        user = User.query.get(customer_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404
            
        return jsonify({
            'customer_id': user.customer_id,
            'mobile_number': user.mobile_number,
            'name': user.name,
            'email': user.email,
            'addresses': user.addresses,
            'kyc_status': user.kyc_status,
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }), 200
    except Exception as e:
        logger.error(f"Error in get_user: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/users/<int:customer_id>', methods=['PUT'])
def update_user(customer_id):
    """Update user details"""
    try:
        user = User.query.get(customer_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404
            
        data = request.json
        if 'name' in data:
            user.name = data['name']
        if 'email' in data:
            user.email = data['email']
        if 'addresses' in data:
            user.addresses = data['addresses']
        if 'kyc_status' in data:
            user.kyc_status = data['kyc_status']
            
        db.session.commit()
        return jsonify({'message': 'User updated successfully'}), 200
    except Exception as e:
        logger.error(f"Error in update_user: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 2. Listing Management
@app.route('/listings', methods=['POST'])
def create_listing():
    """Create a new listing with dimensions"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['customer_id', 'product_type', 'purchase_date', 
                          'invoice_value', 'brand', 'location_pincode', 
                          'length_cm', 'width_cm', 'height_cm']
        
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create new listing
        new_listing = Listing(
            customer_id=data['customer_id'],
            product_type=data['product_type'],
            purchase_date=datetime.strptime(data['purchase_date'], '%Y-%m-%d').date() if isinstance(data['purchase_date'], str) else data['purchase_date'],
            invoice_value=data['invoice_value'],
            brand=data['brand'],
            model_name=data.get('model_name'),
            images=data.get('images'),  # Optional
            location_pincode=data['location_pincode'],
            status=data.get('status', 'Active'),
            length_cm=data['length_cm'],
            width_cm=data['width_cm'],
            height_cm=data['height_cm'],
            weight_kg=data.get('weight_kg', 100)  # Default weight 100kg
        )
        
        db.session.add(new_listing)
        db.session.commit()
        
        return jsonify({
            'message': 'Listing created successfully',
            'listing_id': new_listing.listing_id
        }), 201
    except Exception as e:
        logger.error(f"Error in create_listing: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/listings/<int:listing_id>', methods=['GET'])
def get_listing(listing_id):
    """Get details of a specific listing"""
    try:
        listing = Listing.query.get(listing_id)
        if not listing:
            return jsonify({'message': 'Listing not found'}), 404
            
        return jsonify(listing_to_dict(listing)), 200
    except Exception as e:
        logger.error(f"Error in get_listing: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/listings/<int:listing_id>', methods=['PUT'])
def update_listing(listing_id):
    """Update a listing"""
    try:
        listing = Listing.query.get(listing_id)
        if not listing:
            return jsonify({'message': 'Listing not found'}), 404
            
        data = request.json
        
        # Update fields if provided
        if 'product_type' in data:
            listing.product_type = data['product_type']
        if 'purchase_date' in data:
            listing.purchase_date = datetime.strptime(data['purchase_date'], '%Y-%m-%d').date() if isinstance(data['purchase_date'], str) else data['purchase_date']
        if 'invoice_value' in data:
            listing.invoice_value = data['invoice_value']
        if 'brand' in data:
            listing.brand = data['brand']
        if 'model_name' in data:
            listing.model_name = data['model_name']
        if 'images' in data:
            listing.images = data['images']
        if 'location_pincode' in data:
            listing.location_pincode = data['location_pincode']
        if 'status' in data:
            listing.status = data['status']
        if 'length_cm' in data:
            listing.length_cm = data['length_cm']
        if 'width_cm' in data:
            listing.width_cm = data['width_cm']
        if 'height_cm' in data:
            listing.height_cm = data['height_cm']
        if 'weight_kg' in data:
            listing.weight_kg = data['weight_kg']
            
        db.session.commit()
        return jsonify({'message': 'Listing updated successfully'}), 200
    except Exception as e:
        logger.error(f"Error in update_listing: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/listings', methods=['GET'])
def get_listings():
    """Get listings with optional filters for borrowers"""
    try:
        # Get filter parameters
        product_type = request.args.get('product_type')
        brand = request.args.get('brand')
        min_price = request.args.get('min_price')
        max_price = request.args.get('max_price')
        pincode = request.args.get('pincode')
        distance = request.args.get('distance')  # in km
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        # Start with base query for active listings
        query = Listing.query.filter_by(status='Active')
        
        # Apply filters
        if product_type:
            query = query.filter_by(product_type=product_type)
        if brand:
            query = query.filter_by(brand=brand)
        if min_price:
            query = query.filter(Listing.invoice_value >= min_price)
        if max_price:
            query = query.filter(Listing.invoice_value <= max_price)
            
        # Get paginated results
        paginated_listings = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Process results
        listings_list = []
        for listing in paginated_listings.items:
            listing_dict = listing_to_dict(listing)
            
            # Calculate distance if pincode is provided
            if pincode:
                distance_km = calculate_distance_from_pincodes(pincode, listing.location_pincode)
                listing_dict['distance_km'] = round(distance_km, 2) if distance_km else None
                
                # Filter by distance if specified
                if distance and distance_km and distance_km > float(distance):
                    continue
                    
            listings_list.append(listing_dict)
            
        return jsonify({
            'listings': listings_list,
            'total': paginated_listings.total,
            'pages': paginated_listings.pages,
            'page': page,
            'per_page': per_page
        }), 200
    except Exception as e:
        logger.error(f"Error in get_listings: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/users/<int:customer_id>/listings', methods=['GET'])
def get_user_listings(customer_id):
    """Get all listings created by a specific user (lender dashboard)"""
    try:
        user = User.query.get(customer_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404
            
        listings = Listing.query.filter_by(customer_id=customer_id).all()
        listings_list = [listing_to_dict(listing) for listing in listings]
        
        return jsonify({
            'customer_id': customer_id,
            'listings': listings_list,
            'count': len(listings_list)
        }), 200
    except Exception as e:
        logger.error(f"Error in get_user_listings: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 3. Distance and Cost Calculation
@app.route('/calculate_distance', methods=['GET'])
def calculate_distance():
    """Calculate distance between two pincodes"""
    try:
        pincode1 = request.args.get('pincode1')
        pincode2 = request.args.get('pincode2')
        
        if not pincode1 or not pincode2:
            return jsonify({'error': 'Both pincodes are required'}), 400
            
        distance = calculate_distance_from_pincodes(pincode1, pincode2)
        
        if distance is None:
            return jsonify({'error': 'Invalid pincode(s) or pincode data not found'}), 400
            
        return jsonify({
            'pincode1': pincode1,
            'pincode2': pincode2,
            'distance_km': round(distance, 2)
        }), 200
    except Exception as e:
        logger.error(f"Error in calculate_distance: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/calculate_logistics_cost', methods=['POST'])
def calculate_logistics_cost():
    """Calculate logistics cost based on listing and borrower information"""
    try:
        data = request.json
        
        # Option 1: Using listing_id and borrower_pincode
        if 'listing_id' in data and 'borrower_pincode' in data:
            listing = Listing.query.get(data['listing_id'])
            if not listing:
                return jsonify({'error': 'Listing not found'}), 404
                
            distance = calculate_distance_from_pincodes(listing.location_pincode, data['borrower_pincode'])
            if distance is None:
                return jsonify({'error': 'Invalid pincode(s) or pincode data not found'}), 400
                
            cost = calculate_logistics_cost_from_distance(
                distance, 
                float(listing.length_cm), 
                float(listing.width_cm), 
                float(listing.height_cm), 
                float(listing.weight_kg)
            )
            
            return jsonify({
                'listing_id': listing.listing_id,
                'borrower_pincode': data['borrower_pincode'],
                'lender_pincode': listing.location_pincode,
                'distance_km': round(distance, 2),
                'logistics_cost': cost
            }), 200
            
        # Option 2: Using direct distance and dimensions
        elif 'distance_km' in data and all(k in data for k in ['length_cm', 'width_cm', 'height_cm']):
            cost = calculate_logistics_cost_from_distance(
                float(data['distance_km']),
                float(data['length_cm']),
                float(data['width_cm']),
                float(data['height_cm']),
                float(data.get('weight_kg', 100))
            )
            
            return jsonify({
                'distance_km': float(data['distance_km']),
                'logistics_cost': cost
            }), 200
            
        else:
            return jsonify({'error': 'Invalid request. Provide either listing_id and borrower_pincode OR distance_km and dimensions'}), 400
    except Exception as e:
        logger.error(f"Error in calculate_logistics_cost: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 4. Order Management
@app.route('/orders', methods=['POST'])
def create_order():
    """Create a new order"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['listing_id', 'borrower_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
                
        # Check if listing exists
        listing = Listing.query.get(data['listing_id'])
        if not listing:
            return jsonify({'error': 'Listing not found'}), 404
            
        # Check if borrower exists
        borrower = User.query.get(data['borrower_id'])
        if not borrower:
            return jsonify({'error': 'Borrower not found'}), 404
            
        # Prevent borrowing your own listing
        if listing.customer_id == data['borrower_id']:
            return jsonify({'error': 'Cannot borrow your own listing'}), 400
            
        # Create new order
        new_order = Order(
            listing_id=data['listing_id'],
            borrower_id=data['borrower_id'],
            status='Confirmed',
            rental_price_per_month=data.get('rental_price_per_month'),
            total_rental_price=data.get('total_rental_price'),
            platform_fee=data.get('platform_fee'),
            logistics_fee=data.get('logistics_fee'),
            ancillary_service_fee=data.get('ancillary_service_fee')
        )
        
        # Calculate tax if fees are provided
        if all(new_order.__getattribute__(attr) is not None for attr in ['platform_fee', 'logistics_fee', 'ancillary_service_fee']):
            total_fees = float(new_order.platform_fee) + float(new_order.logistics_fee) + float(new_order.ancillary_service_fee)
            new_order.tax = round(total_fees * 0.18, 2)  # 18% tax
            
        db.session.add(new_order)
        db.session.commit()
        
        return jsonify({
            'message': 'Order created successfully',
            'order_id': new_order.order_id
        }), 201
    except Exception as e:
        logger.error(f"Error in create_order: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get details of a specific order"""
    try:
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'message': 'Order not found'}), 404
            
        return jsonify(order_to_dict(order)), 200
    except Exception as e:
        logger.error(f"Error in get_order: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/orders/<int:order_id>', methods=['PUT'])
def update_order(order_id):
    """Update order details"""
    try:
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'message': 'Order not found'}), 404
            
        data = request.json
        
        # Update pricing fields if provided
        pricing_fields = [
            'rental_price_per_month', 'total_rental_price', 
            'platform_fee', 'logistics_fee', 'ancillary_service_fee'
        ]
        
        for field in pricing_fields:
            if field in data:
                setattr(order, field, data[field])
                
        # Recalculate tax if fees are updated
        if any(field in data for field in ['platform_fee', 'logistics_fee', 'ancillary_service_fee']):
            total_fees = float(order.platform_fee or 0) + float(order.logistics_fee or 0) + float(order.ancillary_service_fee or 0)
            order.tax = round(total_fees * 0.18, 2)  # 18% tax
            
        db.session.commit()
        return jsonify({
            'message': 'Order updated successfully',
            'order': order_to_dict(order)
        }), 200
    except Exception as e:
        logger.error(f"Error in update_order: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/update_order_status', methods=['POST'])
def update_order_status():
    """Update order status and related information"""
    try:
        data = request.json
        if 'order_id' not in data or 'status' not in data:
            return jsonify({'error': 'Order ID and status are required'}), 400
            
        order = Order.query.get(data['order_id'])
        if not order:
            return jsonify({'error': 'Order not found'}), 404
            
        # Update order status
        order.status = data['status']
        
        # Update additional fields based on status
        if data['status'] == 'KYC Done':
            order.kyc_completed_at = datetime.utcnow()
            order.kyc_status = True
        elif data['status'] == 'Payment Made':
            order.payment_datetime = datetime.utcnow()
            
        db.session.commit()
        
        return jsonify({
            'message': 'Order status updated successfully',
            'order': order_to_dict(order)
        }), 200
    except Exception as e:
        logger.error(f"Error in update_order_status: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/users/<int:customer_id>/orders', methods=['GET'])
def get_user_orders(customer_id):
    """Get all orders associated with a user (as either lender or borrower)"""
    try:
        user = User.query.get(customer_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404
            
        # Get orders where user is the borrower
        borrowed_orders = Order.query.filter_by(borrower_id=customer_id).all()
        borrowed_orders_list = [order_to_dict(order) for order in borrowed_orders]
        
        # Get orders where user is the lender
        lent_orders = Order.query.join(Listing).filter(Listing.customer_id == customer_id).all()
        lent_orders_list = [order_to_dict(order) for order in lent_orders]
        
        return jsonify({
            'customer_id': customer_id,
            'borrowed_orders': borrowed_orders_list,
            'lent_orders': lent_orders_list,
            'total_orders': len(borrowed_orders_list) + len(lent_orders_list)
        }), 200
    except Exception as e:
        logger.error(f"Error in get_user_orders: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 5. Delivery Slot Management
@app.route('/schedule_delivery_slot', methods=['POST'])
def schedule_delivery_slot():
    """Schedule a delivery slot for an order"""
    try:
        data = request.json
        
        # Validate required fields
        if 'order_id' not in data or 'slot_datetime' not in data:
            return jsonify({'error': 'Order ID and slot datetime are required'}), 400
            
        # Check if order exists
        order = Order.query.get(data['order_id'])
        if not order:
            return jsonify({'error': 'Order not found'}), 404
            
        # Verify order status (KYC and payment should be done)
        if order.kyc_status is not True or order.payment_datetime is None:
            return jsonify({'error': 'KYC and payment must be completed before scheduling delivery'}), 400
            
        # Parse slot datetime
        try:
            if isinstance(data['slot_datetime'], str):
                slot_datetime = datetime.strptime(data['slot_datetime'], '%Y-%m-%d %H:%M:%S')
            else:
                slot_datetime = data['slot_datetime']
        except ValueError:
            return jsonify({'error': 'Invalid datetime format. Use YYYY-MM-DD HH:MM:SS'}), 400
            
        # Check if slot is in the future
        if slot_datetime < datetime.utcnow():
            return jsonify({'error': 'Delivery slot must be in the future'}), 400
            
        # Check if a slot already exists for this order
        existing_slot = DeliverySlot.query.filter_by(order_id=data['order_id']).first()
        if existing_slot:
            existing_slot.slot_datetime = slot_datetime
            existing_slot.status = data.get('status', 'Scheduled')
        else:
            # Create new delivery slot
            new_slot = DeliverySlot(
                order_id=data['order_id'],
                slot_datetime=slot_datetime,
                status=data.get('status', 'Scheduled')
            )
            db.session.add(new_slot)
            
        # Update order status and logistic slot
        order.status = 'Awaiting Logistics'
        order.logistic_slot = slot_datetime
        
        db.session.commit()
        
        return jsonify({
            'message': 'Delivery slot scheduled successfully',
            'order_id': order.order_id,
            'slot_datetime': slot_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'Scheduled'
        }), 201
    except Exception as e:
        logger.error(f"Error in schedule_delivery_slot: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/delivery_slots/<int:order_id>', methods=['GET'])
def get_delivery_slot(order_id):
    """Get delivery slot information for an order"""
    try:
        slot = DeliverySlot.query.filter_by(order_id=order_id).first()
        if not slot:
            return jsonify({'message': 'No delivery slot found for this order'}), 404
            
        return jsonify({
            'slot_id': slot.slot_id,
            'order_id': slot.order_id,
            'slot_datetime': slot.slot_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            'status': slot.status,
            'created_at': slot.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }), 200
    except Exception as e:
        logger.error(f"Error in get_delivery_slot: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/update_delivery_slot', methods=['POST'])
def update_delivery_slot_status():
    """Update the status of a delivery slot"""
    try:
        data = request.json
        
        if 'slot_id' not in data or 'status' not in data:
            return jsonify({'error': 'Slot ID and status are required'}), 400
            
        slot = DeliverySlot.query.get(data['slot_id'])
        if not slot:
            return jsonify({'error': 'Delivery slot not found'}), 404
            
        slot.status = data['status']
        
        # Update order status if delivery completed
        if data['status'] == 'Completed':
            order = Order.query.get(slot.order_id)
            if order:
                order.status = 'Delivered'
                
        db.session.commit()
        
        return jsonify({
            'message': 'Delivery slot status updated successfully',
            'slot_id': slot.slot_id,
            'status': slot.status
        }), 200
    except Exception as e:
        logger.error(f"Error in update_delivery_slot_status: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 6. Pincode Master Data Management
@app.route('/import_pincode_data', methods=['POST'])
def import_pincode_data():
    """Import pincode data from CSV file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
            
        if file and file.filename.endswith('.csv'):
            import csv
            import io
            
            # Read CSV data
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_data = csv.reader(stream)
            
            # Skip header
            next(csv_data, None)
            
            # Import data
            count = 0
            for row in csv_data:
                if len(row) >= 5:  # Ensure row has enough columns
                    pincode, latitude, longitude, district, state = row[:5]
                    
                    # Check if pincode already exists
                    existing = PincodeMaster.query.get(pincode)
                    if existing:
                        # Update existing record
                        existing.latitude = latitude
                        existing.longitude = longitude
                        existing.district = district
                        existing.state_name = state
                    else:
                        # Create new record
                        new_pincode = PincodeMaster(
                            pincode=pincode,
                            latitude=latitude,
                            longitude=longitude,
                            district=district,
                            state_name=state
                        )
                        db.session.add(new_pincode)
                        
                    count += 1
                    
                    # Commit in batches to avoid memory issues
                    if count % 1000 == 0:
                        db.session.commit()
                        
            # Final commit
            db.session.commit()
            
            return jsonify({
                'message': 'Pincode data imported successfully',
                'records_processed': count
            }), 200
        else:
            return jsonify({'error': 'File must be a CSV'}), 400
    except Exception as e:
        logger.error(f"Error in import_pincode_data: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/pincodes', methods=['GET'])
def search_pincodes():
    """Search pincodes by pincode, district or state"""
    try:
        query = request.args.get('q', '')
        limit = int(request.args.get('limit', 10))
        
        results = PincodeMaster.query.filter(
            (PincodeMaster.pincode.like(f'%{query}%')) |
            (PincodeMaster.district.like(f'%{query}%')) |
            (PincodeMaster.state_name.like(f'%{query}%'))
        ).limit(limit).all()
        
        pincodes = [{
            'pincode': p.pincode,
            'latitude': float(p.latitude),
            'longitude': float(p.longitude),
            'district': p.district,
            'state_name': p.state_name
        } for p in results]
        
        return jsonify({
            'pincodes': pincodes,
            'count': len(pincodes)
        }), 200
    except Exception as e:
        logger.error(f"Error in search_pincodes: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/calculate_rent', methods=['POST'])
def rent_calculation():
    try:
        data = request.get_json()
        
        # Required fields
        invoice_value = data.get('invoice_value')
        purchase_date = data.get('purchase_date')
        
        # Optional fields
        image_url = data.get('image_url')
        
        # Validate required inputs
        if not invoice_value or not purchase_date:
            return jsonify({"error": "Missing required fields: invoice_value and purchase_date are required"}), 400
        
        # Process image if URL is provided
        condition_details = None
        if image_url:
            logging.info(f"Analyzing image: {image_url}")
            condition_details = analyze_image(image_url)
            logging.info(f"Image analysis results: {condition_details}")
        
        # Calculate rent
        rent = calculate_rent(invoice_value, purchase_date, condition_details)
        
        # Prepare response
        response = {
            "monthly_rent": rent,
            "invoice_value": invoice_value,
            "age_in_months": (datetime.today() - datetime.strptime(purchase_date, "%Y-%m-%d")).days // 30
        }
        
        # Include condition details in response if available
        if condition_details:
            response["condition_details"] = condition_details
        
        return jsonify(response)
    
    except Exception as e:
        logging.error(f"Error processing request: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Payment Account Management - Proxy route to payment service
@app.route('/payment_accounts', methods=['POST'])
def add_payment_account_proxy():
    """Proxy route to add/update payment account"""
    try:
        # Forward request to payment service
        response = requests.post(
            f"{PAYMENT_API_URL}/payment_accounts",
            json=request.json,
            headers={'Content-Type': 'application/json'}
        )
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Error in add_payment_account_proxy: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/users/<int:customer_id>/payment_accounts', methods=['GET'])
def get_payment_accounts_proxy(customer_id):
    """Proxy route to get user payment accounts"""
    try:
        # Forward request to payment service
        response = requests.get(
            f"{PAYMENT_API_URL}/users/{customer_id}/payment_accounts"
        )
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Error in get_payment_accounts_proxy: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/payment_accounts/<int:account_id>', methods=['DELETE'])
def delete_payment_account_proxy(account_id):
    """Proxy route to delete payment account"""
    try:
        # Forward request to payment service
        response = requests.delete(
            f"{PAYMENT_API_URL}/payment_accounts/{account_id}"
        )
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Error in delete_payment_account_proxy: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 2. Account Verification - Proxy routes
@app.route('/verify_account', methods=['POST'])
def verify_account_proxy():
    """Proxy route to initiate account verification"""
    try:
        # Forward request to payment service
        response = requests.post(
            f"{PAYMENT_API_URL}/verify_account",
            json=request.json,
            headers={'Content-Type': 'application/json'}
        )
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Error in verify_account_proxy: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/verification_status/<int:verification_id>', methods=['GET'])
def check_verification_status_proxy(verification_id):
    """Proxy route to check verification status"""
    try:
        # Forward request to payment service
        response = requests.get(
            f"{PAYMENT_API_URL}/verification_status/{verification_id}"
        )
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Error in check_verification_status_proxy: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 3. Payout Management - Proxy routes
@app.route('/create_payout', methods=['POST'])
def create_payout_proxy():
    """Proxy route to create a payout"""
    try:
        # Forward request to payment service
        response = requests.post(
            f"{PAYMENT_API_URL}/create_payout",
            json=request.json,
            headers={'Content-Type': 'application/json'}
        )
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Error in create_payout_proxy: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/payout_status/<int:payout_id>', methods=['GET'])
def get_payout_status_proxy(payout_id):
    """Proxy route to get payout status"""
    try:
        # Forward request to payment service
        response = requests.get(
            f"{PAYMENT_API_URL}/payout_status/{payout_id}"
        )
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Error in get_payout_status_proxy: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Run the application
#if __name__ == '__main__':
#    context = ('cert.pem', 'key.pem')  # Path to your certificate files
#    app.run(host="0.0.0.0", port=5000, debug=True)
