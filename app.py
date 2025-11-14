from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Cart
import os
import json
import uuid
import qrcode
from io import BytesIO
from dotenv import load_dotenv
from flask import session, request, jsonify
from yolo_detection import YOLODetector
import cv2
import time

# Coupon codes dictionary
COUPON_CODES = {
    'WELCOME10': {'type': 'percentage', 'value': 10, 'min_amount': 100, 'description': '10% off on orders above ₹100'},
    'SAVE50': {'type': 'fixed', 'value': 50, 'min_amount': 200, 'description': '₹50 off on orders above ₹200'},
    'FIRST20': {'type': 'percentage', 'value': 20, 'min_amount': 150, 'description': '20% off for first-time users'},
    'MEGA25': {'type': 'percentage', 'value': 25, 'min_amount': 500, 'description': '25% off on orders above ₹500'},
}

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:password@localhost:5432/visioncart_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

items_data = {}
with open('static/data/items.json', 'r') as f:
    items_data = json.load(f)

qr_tokens = {}

# Global detector instance
detector = YOLODetector()
model_loaded = detector.initialize()

if not model_loaded:
    print("⚠️  WARNING: YOLO model not loaded. Camera detection will not work.")
    print("⚠️  You can still use manual item entry to test the cart system.")
else:
    print("✓ YOLO model ready for detection!")

# Track currently visible items per cart
currently_visible_items = {}  # {cart_id: {item_name: last_seen_time}}
ITEM_TIMEOUT = 1.5  # seconds - if item not seen for this long, remove it

def normalize_item_name(detected_name):
    """
    Normalize detected item name by removing _front/_back suffix
    Returns: (normalized_name, original_name, price, weight)
    """
    detected_lower = detected_name.lower()
    
    # Check if item exists exactly as detected
    if detected_lower in items_data:
        price, weight = items_data[detected_lower]
        return detected_lower, detected_lower, price, weight
    
    # Try removing _front or _back suffix
    for suffix in ['_front', '_back']:
        if detected_lower.endswith(suffix):
            base_name = detected_lower[:-len(suffix)]
            # Check if base name with any suffix exists
            for key in items_data.keys():
                if key.startswith(base_name):
                    price, weight = items_data[key]
                    return base_name, key, price, weight
    
    return None, None, None, None

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')

        if User.query.filter_by(email=email).first():
            if request.is_json:
                return jsonify({'success': False, 'message': 'Email already exists'}), 400
            return render_template('signup.html', error='Email already exists')

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        if request.is_json:
            return jsonify({'success': True, 'message': 'User created successfully'})
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email')
        password = data.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            cart_id = str(uuid.uuid4())
            session['cart_id'] = cart_id
            session['cart_items'] = []
            session['cart_total'] = 0

            if request.is_json:
                return jsonify({'success': True, 'redirect': url_for('home')})
            return redirect(url_for('home'))

        if request.is_json:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        return render_template('login.html', error='Invalid email or password')

    return render_template('login.html')

@app.route('/home')
@login_required
def home():
    if 'cart_id' not in session:
        session['cart_id'] = str(uuid.uuid4())
        session['cart_items'] = []
        session['cart_total'] = 0
    return render_template('home.html', cart_id=session['cart_id'])

@app.route('/detect', methods=['POST'])
@login_required
def detect():
    try:
        detected_item = request.json.get('item', '').lower()
        
        # Normalize the item name and get price/weight
        normalized_name, original_key, price, weight = normalize_item_name(detected_item)

        if normalized_name:
            cart_items = session.get('cart_items', [])

            # Check if item already exists in cart (using normalized name)
            existing_item = next((item for item in cart_items if item['name'] == normalized_name), None)
            if existing_item:
                existing_item['quantity'] += 1
                existing_item['total'] = existing_item['quantity'] * existing_item['price']
            else:
                cart_items.append({
                    'name': normalized_name,
                    'price': price,
                    'weight': weight,
                    'quantity': 1,
                    'total': price
                })

            session['cart_items'] = cart_items
            session['cart_total'] = sum(item['total'] for item in cart_items)
            session.modified = True

            return jsonify({
                'success': True,
                'item': normalized_name,
                'price': price,
                'weight': weight,
                'cart': cart_items,
                'total': session['cart_total']
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Item "{detected_item}" not found in database'
            }), 404

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/update-visible-items', methods=['POST'])
@login_required
def update_visible_items():
    """Update cart based on currently visible items"""
    try:
        data = request.get_json()
        visible_items = data.get('visible_items', [])  # List of item names currently visible
        
        cart_items = session.get('cart_items', [])
        items_dict = {item['name']: item for item in cart_items}
        
        # Get all normalized item names with their prices/weights
        visible_items_data = {}
        for item_name in visible_items:
            normalized_name, original_key, price, weight = normalize_item_name(item_name)
            if normalized_name:
                visible_items_data[normalized_name] = {'price': price, 'weight': weight}
        
        # Add or ensure items that are visible
        for item_name, item_data in visible_items_data.items():
            if item_name not in items_dict:
                # Add new item
                items_dict[item_name] = {
                    'name': item_name,
                    'price': item_data['price'],
                    'weight': item_data['weight'],
                    'quantity': 1,
                    'total': item_data['price']
                }
        
        # Remove items that are no longer visible
        items_to_remove = []
        for item_name in items_dict.keys():
            if item_name not in visible_items_data:
                items_to_remove.append(item_name)
        
        for item_name in items_to_remove:
            del items_dict[item_name]
        
        # Update session
        cart_items = list(items_dict.values())
        session['cart_items'] = cart_items
        session['cart_total'] = sum(item['total'] for item in cart_items)
        session.modified = True
        
        return jsonify({
            'success': True,
            'cart': cart_items,
            'total': session['cart_total']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Display payment options page with correct total including coupon discount"""
    print("=== CHECKOUT ROUTE ACCESSED ===")
    print(f"User: {current_user.email}")
    print(f"Cart ID: {session.get('cart_id')}")
    
    cart_items = session.get('cart_items', [])
    print(f"Cart items: {cart_items}")
    print(f"Number of items: {len(cart_items)}")
    
    if not cart_items:
        print("ERROR: Cart is empty! Redirecting to home")
        return redirect(url_for('home'))
    
    # Calculate subtotal
    subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
    print(f"Subtotal: {subtotal}")
    
    # Get applied coupon and calculate final total
    applied_coupon = session.get('applied_coupon')
    print(f"Applied coupon: {applied_coupon}")
    
    if applied_coupon:
        total_amount = applied_coupon.get('final_total', round(subtotal, 2))
        discount_amount = applied_coupon.get('discount_amount', 0)
    else:
        total_amount = round(subtotal, 2)
        discount_amount = 0
    
    print(f"Total amount: {total_amount}")
    print(f"Discount: {discount_amount}")
    
    # Store the final amount in session for payment processing
    session['checkout_total'] = total_amount
    session['checkout_discount'] = discount_amount
    session.modified = True
    
    print("Rendering payment.html")
    
    # Show payment options page (payment.html)
    return render_template('payment.html',
                          cart_items=cart_items,
                          total_amount=total_amount,
                          discount_amount=discount_amount,
                          applied_coupon=applied_coupon,
                          cart_id=session.get('cart_id'))


@app.route('/complete-payment', methods=['POST'])
@login_required
def complete_payment():
    """Complete payment and clear cart with coupon"""
    try:
        data = request.get_json()
        payment_method = data.get('payment_method')
        cart_id = data.get('cart_id')
        
        cart_items = session.get('cart_items', [])
        
        if not cart_items:
            return jsonify({'success': False, 'message': 'Cart is empty'}), 400
        
        # Use the checkout total (with coupon applied) instead of cart_total
        final_amount = session.get('checkout_total', session.get('cart_total', 0))
        discount_applied = session.get('checkout_discount', 0)
        applied_coupon = session.get('applied_coupon')
        
        # Save cart with correct final amount
        cart = Cart(
            cart_id=cart_id,
            user_id=current_user.id,
            items=cart_items,
            total_amount=final_amount  # This now includes the coupon discount
        )
        db.session.add(cart)
        db.session.commit()
        
        # Clear everything from session
        new_cart_id = str(uuid.uuid4())
        session['cart_id'] = new_cart_id
        session['cart_items'] = []
        session['cart_total'] = 0
        session['applied_coupon'] = None  # Clear coupon
        session['checkout_total'] = 0
        session['checkout_discount'] = 0
        session.modified = True
        
        return jsonify({
            'success': True,
            'message': f'Payment of ₹{final_amount:.2f} via {payment_method} completed successfully',
            'discount_saved': discount_applied,
            'new_cart_id': new_cart_id
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/qr')
@login_required
def generate_qr():
    token = str(uuid.uuid4())
    qr_tokens[token] = {
        'user_id': current_user.id,
        'cart_id': session.get('cart_id'),
        'cart_items': session.get('cart_items', []),
        'cart_total': session.get('cart_total', 0)
    }

    qr_url = f"http://{request.host}/qr-login?token={token}"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return send_file(buf, mimetype='image/png')


@app.route('/payment-qr/<cart_id>')
@login_required
def generate_payment_qr(cart_id):
    """Generate QR code for UPI payment"""
    cart_items = session.get('cart_items', [])

    # ✅ Prefer discounted total if available
    final_total = session.get('checkout_total', session.get('cart_total', 0))

    # Create payment token
    payment_token = str(uuid.uuid4())
    qr_tokens[payment_token] = {
        'type': 'payment',
        'cart_id': cart_id,
        'cart_items': cart_items,
        'cart_total': final_total  # ✅ store discounted total
    }

    # Generate URL for mobile payment page using local IP
    import socket
    local_ip = socket.gethostbyname(socket.gethostname())
    payment_url = f"http://{local_ip}:5000/mobile-payment?token={payment_token}"

    # Generate QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(payment_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return send_file(buf, mimetype='image/png')


@app.route('/mobile-payment')
def mobile_payment():
    """Display payment details on mobile after scanning QR"""
    token = request.args.get('token')
    
    if token not in qr_tokens:
        return "Invalid or expired payment link", 400
    
    payment_data = qr_tokens[token]
    
    if payment_data.get('type') != 'payment':
        return "Invalid payment token", 400
    
    return render_template('mobile_payment.html',
                         cart_id=payment_data['cart_id'],
                         cart_items=payment_data['cart_items'],
                         total_amount=payment_data['cart_total'])

@app.route('/qr-login')
def qr_login():
    token = request.args.get('token')

    if token not in qr_tokens:
        return "Invalid or expired QR code", 400

    token_data = qr_tokens[token]
    user = User.query.get(token_data['user_id'])

    if user:
        login_user(user)
        session['cart_id'] = token_data['cart_id']
        session['cart_items'] = token_data['cart_items']
        session['cart_total'] = token_data['cart_total']

        del qr_tokens[token]

        return redirect(url_for('home'))

    return "User not found", 404

@app.route('/history')
@login_required
def history():
    carts = Cart.query.filter_by(user_id=current_user.id).order_by(Cart.created_at.desc()).all()
    return render_template('history.html', carts=carts)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

@app.route('/remove-item', methods=['POST'])
@login_required
def remove_item():
    try:
        item_name = request.json.get('item_name')
        cart_items = session.get('cart_items', [])

        cart_items = [item for item in cart_items if item['name'] != item_name]

        session['cart_items'] = cart_items
        session['cart_total'] = sum(item['total'] for item in cart_items)

        return jsonify({
            'success': True,
            'cart': cart_items,
            'total': session['cart_total']
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

def generate_frames(cart_id):
    """Generator function for video streaming with YOLO detection"""
    camera = cv2.VideoCapture(0)
    
    if not camera.isOpened():
        print("Error: Cannot access webcam")
        return
    
    # Initialize tracking for this cart
    if cart_id not in currently_visible_items:
        currently_visible_items[cart_id] = {}
    
    try:
        while True:
            success, frame = camera.read()
            if not success:
                break
            
            current_time = time.time()
            
            # Only perform detection if model is loaded
            if detector.is_initialized:
                # Perform YOLO detection
                detections = detector.detect(frame)
                
                # Track currently visible items in this frame
                current_frame_items = set()
                
                if detections:
                    for det in detections:
                        detected_class = det['class']
                        confidence = det['confidence']
                        
                        # Draw detection on frame
                        label = f"{detected_class}: {confidence:.2f}"
                        cv2.putText(frame, label, (10, 30), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        # Normalize and check if item exists in items.json
                        normalized_name, original_key, price, weight = normalize_item_name(detected_class)
                        
                        if normalized_name:
                            # Update last seen time for this item
                            currently_visible_items[cart_id][normalized_name] = current_time
                            current_frame_items.add(normalized_name)
                            
                            cv2.putText(frame, f"DETECTED: Rs.{price} ({weight}kg)", (10, 60), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        else:
                            cv2.putText(frame, "Item not in database", (10, 60), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                
                # Remove items that haven't been seen recently
                items_to_remove = []
                for item_name, last_seen in currently_visible_items[cart_id].items():
                    if current_time - last_seen > ITEM_TIMEOUT:
                        items_to_remove.append(item_name)
                
                for item_name in items_to_remove:
                    del currently_visible_items[cart_id][item_name]
                
                # Display count of currently tracked items
                tracked_count = len(currently_visible_items[cart_id])
                cv2.putText(frame, f"Items in view: {tracked_count}", (10, 90), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            else:
                # Show warning if model not loaded
                cv2.putText(frame, "YOLO Model Not Loaded", (10, 30), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.putText(frame, "Use Manual Entry", (10, 60), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
                
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    finally:
        camera.release()
        # Clean up tracking data
        if cart_id in currently_visible_items:
            del currently_visible_items[cart_id]

# def generate_frames(cart_id):
#     """Generator function for video streaming with YOLO detection"""
#     # Try different camera indices to find Camo Studio
#     # Camo Studio is usually at index 1, 2, or 3
#     camera = None
#     camera_indices = [1, 2, 3, 0]  # Try these indices in order
    
#     for idx in camera_indices:
#         camera = cv2.VideoCapture(idx)
#         if camera.isOpened():
#             print(f"✓ Camera opened successfully at index {idx}")
#             break
#         camera.release()
    
#     if not camera or not camera.isOpened():
#         print("Error: Cannot access any webcam")
#         return
    
#     # Optional: Set camera resolution for better quality
#     camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
#     camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
#     # Initialize tracking for this cart
#     if cart_id not in currently_visible_items:
#         currently_visible_items[cart_id] = {}
    
#     try:
#         while True:
#             success, frame = camera.read()
#             if not success:
#                 break
            
#             current_time = time.time()
            
#             # Only perform detection if model is loaded
#             if detector.is_initialized:
#                 # Perform YOLO detection
#                 detections = detector.detect(frame)
                
#                 # Track currently visible items in this frame
#                 current_frame_items = set()
                
#                 if detections:
#                     for det in detections:
#                         detected_class = det['class']
#                         confidence = det['confidence']
                        
#                         # Draw detection on frame
#                         label = f"{detected_class}: {confidence:.2f}"
#                         cv2.putText(frame, label, (10, 30), 
#                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
#                         # Normalize and check if item exists in items.json
#                         normalized_name, original_key, price, weight = normalize_item_name(detected_class)
                        
#                         if normalized_name:
#                             # Update last seen time for this item
#                             currently_visible_items[cart_id][normalized_name] = current_time
#                             current_frame_items.add(normalized_name)
                            
#                             cv2.putText(frame, f"DETECTED: Rs.{price} ({weight}kg)", (10, 60), 
#                                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
#                         else:
#                             cv2.putText(frame, "Item not in database", (10, 60), 
#                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                
#                 # Remove items that haven't been seen recently
#                 items_to_remove = []
#                 for item_name, last_seen in currently_visible_items[cart_id].items():
#                     if current_time - last_seen > ITEM_TIMEOUT:
#                         items_to_remove.append(item_name)
                
#                 for item_name in items_to_remove:
#                     del currently_visible_items[cart_id][item_name]
                
#                 # Display count of currently tracked items
#                 tracked_count = len(currently_visible_items[cart_id])
#                 cv2.putText(frame, f"Items in view: {tracked_count}", (10, 90), 
#                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
#             else:
#                 # Show warning if model not loaded
#                 cv2.putText(frame, "YOLO Model Not Loaded", (10, 30), 
#                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
#                 cv2.putText(frame, "Use Manual Entry", (10, 60), 
#                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
#             # Encode frame as JPEG
#             ret, buffer = cv2.imencode('.jpg', frame)
#             if not ret:
#                 continue
                
#             frame_bytes = buffer.tobytes()
#             yield (b'--frame\r\n'
#                    b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
#     finally:
#         camera.release()
#         # Clean up tracking data
#         if cart_id in currently_visible_items:
#             del currently_visible_items[cart_id]

# @app.route('/validate-coupon', methods=['POST'])
# @login_required
# def validate_coupon():
#     """Validate and apply coupon code"""
#     try:
#         data = request.get_json()
#         coupon_code = data.get('coupon_code', '').upper().strip()
#         cart_total = session.get('cart_total', 0)
        
#         if not coupon_code:
#             return jsonify({'success': False, 'message': 'Please enter a coupon code'}), 400
        
#         if coupon_code not in COUPON_CODES:
#             return jsonify({'success': False, 'message': 'Invalid coupon code'}), 400
        
#         coupon = COUPON_CODES[coupon_code]
        
#         # Check minimum amount
#         if cart_total < coupon['min_amount']:
#             return jsonify({
#                 'success': False, 
#                 'message': f'Minimum order of ₹{coupon["min_amount"]} required'
#             }), 400
        
#         # Calculate discount
#         if coupon['type'] == 'percentage':
#             discount_amount = (cart_total * coupon['value']) / 100
#         else:  # fixed
#             discount_amount = coupon['value']
        
#         # Ensure discount doesn't exceed cart total
#         discount_amount = min(discount_amount, cart_total)
        
#         final_total = cart_total - discount_amount
        
#         # Store coupon in session
#         session['applied_coupon'] = {
#             'code': coupon_code,
#             'discount_amount': discount_amount,
#             'original_total': cart_total,
#             'final_total': final_total
#         }
#         session.modified = True
        
#         return jsonify({
#             'success': True,
#             'message': f'Coupon applied! You saved ₹{discount_amount:.2f}',
#             'coupon_code': coupon_code,
#             'discount_amount': discount_amount,
#             'original_total': cart_total,
#             'final_total': final_total,
#             'description': coupon['description']
#         })
        
#     except Exception as e:
#         return jsonify({'success': False, 'message': str(e)}), 500

from flask import session, request, jsonify

@app.route('/validate-coupon', methods=['POST'])
@login_required
def validate_coupon():
    """Validate and apply coupon code with minimum amount check"""
    try:
        data = request.get_json()
        coupon_code = data.get('coupon_code', '').upper().strip()
        
        # Load cart from session
        cart_items = session.get('cart_items', [])
        subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
        
        if not coupon_code:
            return jsonify({'success': False, 'message': 'Please enter a coupon code'}), 400
        
        # Check if coupon exists
        if coupon_code not in COUPON_CODES:
            return jsonify({'success': False, 'message': 'Invalid coupon code'}), 400
        
        coupon = COUPON_CODES[coupon_code]
        
        # ✅ Check minimum amount requirement
        if subtotal < coupon['min_amount']:
            return jsonify({
                'success': False, 
                'message': f'Minimum order of ₹{coupon["min_amount"]} required for this coupon'
            }), 400
        
        # Calculate discount based on coupon type
        if coupon['type'] == 'percentage':
            discount_amount = (subtotal * coupon['value']) / 100
        else:  # fixed discount
            discount_amount = coupon['value']
        
        # Ensure discount doesn't exceed cart total
        discount_amount = min(discount_amount, subtotal)
        final_total = subtotal - discount_amount
        
        # Store coupon in session
        session['applied_coupon'] = {
            'coupon_code': coupon_code,
            'discount_amount': round(discount_amount, 2),
            'original_total': round(subtotal, 2),
            'final_total': round(final_total, 2)
        }
        session.modified = True
        
        return jsonify({
            'success': True,
            'message': f'Coupon {coupon_code} applied! You saved ₹{discount_amount:.2f}',
            'coupon_code': coupon_code,
            'discount_amount': round(discount_amount, 2),
            'original_total': round(subtotal, 2),
            'final_total': round(final_total, 2),
            'description': coupon['description']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/remove-coupon', methods=['POST'])
@login_required
def remove_coupon():
    """Remove applied coupon"""
    try:
        session.pop('applied_coupon', None)
        return jsonify(success=True, message="Coupon removed")
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/get-cart', methods=['GET'])
@login_required
def get_cart():
    """Get cart with proper coupon calculation"""
    cart_items = session.get('cart_items', [])
    subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
    
    applied_coupon = session.get('applied_coupon')
    
    # Recalculate discount to ensure consistency
    if applied_coupon and cart_items:
        coupon_code = applied_coupon.get('coupon_code', '')
        
        # Validate coupon is still applicable
        if coupon_code in COUPON_CODES:
            coupon = COUPON_CODES[coupon_code]
            
            # Check if cart still meets minimum
            if subtotal >= coupon['min_amount']:
                # Recalculate discount
                if coupon['type'] == 'percentage':
                    discount_amount = (subtotal * coupon['value']) / 100
                else:
                    discount_amount = coupon['value']
                
                discount_amount = min(discount_amount, subtotal)
                final_total = subtotal - discount_amount
                
                # Update session with recalculated values
                applied_coupon['discount_amount'] = round(discount_amount, 2)
                applied_coupon['final_total'] = round(final_total, 2)
                session['applied_coupon'] = applied_coupon
                session.modified = True
            else:
                # Cart no longer meets minimum, remove coupon
                session.pop('applied_coupon', None)
                applied_coupon = None
        else:
            # Invalid coupon, remove it
            session.pop('applied_coupon', None)
            applied_coupon = None
    
    return jsonify({
        'cart_items': cart_items,
        'cart_total': round(subtotal, 2),
        'applied_coupon': applied_coupon
    })

@app.route('/video_feed')
@login_required
def video_feed():
    """Video streaming route"""
    cart_id = session.get('cart_id', 'anonymous')
    return Response(generate_frames(cart_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get-visible-items', methods=['GET'])
@login_required
def get_visible_items():
    """Get list of currently visible items for this cart"""
    cart_id = session.get('cart_id', 'anonymous')
    visible = list(currently_visible_items.get(cart_id, {}).keys())
    return jsonify({'visible_items': visible})

@app.route('/get-available-items', methods=['GET'])
@login_required
def get_available_items():
    """Return list of available items for reference"""
    items_list = []
    seen_items = set()
    
    for key, (price, weight) in items_data.items():
        # Remove _front/_back suffix for display
        base_name = key.replace('_front', '').replace('_back', '')
        if base_name not in seen_items:
            items_list.append({
                'name': base_name,
                'price': price,
                'weight': weight
            })
            seen_items.add(base_name)
    
    return jsonify({'items': items_list})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)