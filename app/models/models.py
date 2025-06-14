# Models extracted


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