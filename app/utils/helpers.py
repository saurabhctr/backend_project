# Utility functions


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