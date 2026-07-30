import os
import math
import time
import urllib.parse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import database

app = Flask(__name__)
app.secret_key = 'foodbridge_super_secret_key_change_in_production'

# -------------------------------------------------------
# GMAIL SMTP CONFIGURATION
# Set these environment variables OR fill them directly.
# Gmail Setup: Google Account → Security → App Passwords
# App Password: 16-character code (no spaces) from Gmail.
# -------------------------------------------------------
MAIL_SENDER_EMAIL = os.environ.get('MAIL_SENDER_EMAIL', 'your_gmail@gmail.com')
MAIL_APP_PASSWORD  = os.environ.get('MAIL_APP_PASSWORD',  'xxxx xxxx xxxx xxxx')  # Replace with your 16-char Gmail App Password
MAIL_SENDER_NAME  = 'FoodBridge Platform'

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Register teardown function to close DB connections
app.teardown_appcontext(database.close_connection)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------------------------------------
# AUTHENTICATION DECORATORS & CONTEXT INJECTION
# ----------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'admin':
            flash('This action requires Administrator privileges.', 'danger')
            return redirect(url_for('donations'))
        return f(*args, **kwargs)
    return decorated_function

def donor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') not in ['donor', 'admin']:
            flash('This action is restricted to Food Donors and Admins.', 'danger')
            return redirect(url_for('donations'))
        return f(*args, **kwargs)
    return decorated_function

def ngo_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') not in ['ngo', 'admin']:
            flash('This action is restricted to NGOs and Admins.', 'danger')
            return redirect(url_for('donations'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    """Make current user info and unread notifications available in all HTML templates."""
    context = {'current_user': None, 'unread_notifications_count': 0}
    if 'user_id' in session:
        db = database.get_db()
        unread_count = db.execute(
            'SELECT COUNT(*) as c FROM notifications WHERE user_id = ? AND is_read = 0',
            (session['user_id'],)
        ).fetchone()['c']
        
        user_info = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        context['current_user'] = {
            'id': session.get('user_id'),
            'name': session.get('user_name'),
            'email': session.get('user_email'),
            'role': session.get('user_role'),
            'organization': session.get('user_organization'),
            'availability': user_info.get('availability') if user_info else 'Online',
            'daily_capacity': user_info.get('daily_capacity') if user_info else 0,
            'capacity_used': user_info.get('current_capacity_used') if user_info else 0
        }
        context['unread_notifications_count'] = unread_count
    return context

# ----------------------------------------------------
# HELPER FUNCTIONS: DISTANCE, MATCHING & NOTIFICATIONS
# ----------------------------------------------------

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great-circle distance between two points in kilometers."""
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (ValueError, TypeError):
        return 0.0
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def auto_reset_daily_capacity():
    """Reset every NGO's current_capacity_used to 0 once per day.
    
    Compares today's date (YYYY-MM-DD) against the stored capacity_reset_date.
    If the date has changed (i.e. a new day), resets the counter automatically.
    This runs silently before any NGO matching – no manual reset needed.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    db = database.get_db()
    # Find NGOs whose reset date is NOT today
    stale_ngos = db.execute(
        "SELECT id FROM users WHERE role = 'ngo' AND (capacity_reset_date IS NULL OR capacity_reset_date != ?)",
        (today,)
    ).fetchall()
    if stale_ngos:
        db.execute(
            "UPDATE users SET current_capacity_used = 0, capacity_reset_date = ? WHERE role = 'ngo' AND (capacity_reset_date IS NULL OR capacity_reset_date != ?)",
            (today, today)
        )
        db.commit()
        print(f"[Daily Reset] Capacity counter reset for {len(stale_ngos)} NGO(s) on {today}.")

def find_nearby_ngos(donor_lat, donor_lng):
    """Find online NGOs within their service radius of the donor location.
    Auto-resets daily capacity counters before matching.
    """
    auto_reset_daily_capacity()  # Reset counters if a new day has started
    db = database.get_db()
    ngos = db.execute("SELECT * FROM users WHERE role = 'ngo' AND availability = 'Online'").fetchall()
    matched = []
    for ngo in ngos:
        n_lat = ngo['latitude'] if ngo['latitude'] is not None else 12.9716
        n_lng = ngo['longitude'] if ngo['longitude'] is not None else 77.5946
        radius = ngo['service_radius_km'] if ngo['service_radius_km'] is not None else 10.0
        dist = haversine(donor_lat, donor_lng, n_lat, n_lng)
        if dist <= radius:
            rem_cap = max(0, (ngo['daily_capacity'] or 500) - (ngo['current_capacity_used'] or 0))
            matched.append({
                'ngo': ngo,
                'distance_km': round(dist, 2),
                'available_capacity': rem_cap
            })
    matched.sort(key=lambda x: x['distance_km'])
    return matched

def create_notification(user_id, title, message, link='#', type_str='info'):
    """Create in-app notification for a user."""
    db = database.get_db()
    db.execute('''
        INSERT INTO notifications (user_id, title, message, link, type, is_read)
        VALUES (?, ?, ?, ?, ?, 0)
    ''', (user_id, title, message, link, type_str))
    db.commit()

def send_email_notification(to_email, subject, body):
    """Send a real email via Gmail SMTP using an App Password.
    
    To enable:
    1. Go to your Google Account → Security → 2-Step Verification (must be ON).
    2. Then go to Security → App Passwords.
    3. Generate an App Password for 'Mail' on 'Other device'.
    4. Set MAIL_SENDER_EMAIL and MAIL_APP_PASSWORD in environment variables
       OR replace the defaults in the config block above.
    """
    # Check if credentials are configured
    if MAIL_APP_PASSWORD in ('xxxx xxxx xxxx xxxx', '') or MAIL_SENDER_EMAIL == 'your_gmail@gmail.com':
        # Fallback: just log to console when credentials not set
        print(f"\n[EMAIL - NOT SENT - Configure Gmail credentials]\nTO: {to_email}\nSUBJECT: {subject}\nBODY:\n{body}\n")
        return

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"{MAIL_SENDER_NAME} <{MAIL_SENDER_EMAIL}>"
        msg['To']      = to_email

        # Plain-text body
        msg.attach(MIMEText(body, 'plain'))

        # HTML-styled body
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;">
            <div style="background: linear-gradient(135deg, #0f172a, #1e293b); padding: 24px;">
                <h2 style="color: white; margin: 0;">🌱 FoodBridge Platform Alert</h2>
            </div>
            <div style="padding: 24px; background: #f8fafc;">
                <pre style="font-family: Arial, sans-serif; white-space: pre-wrap; color: #334155; line-height: 1.6;">{body}</pre>
            </div>
            <div style="background: #e2e8f0; padding: 12px 24px; text-align: center; font-size: 12px; color: #64748b;">
                FoodBridge MVP 2.0 — Automated Food Rescue Platform
            </div>
        </div>
        """
        msg.attach(MIMEText(html_body, 'html'))

        # Send via Gmail SMTP SSL on port 465
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MAIL_SENDER_EMAIL, MAIL_APP_PASSWORD)
            server.sendmail(MAIL_SENDER_EMAIL, to_email, msg.as_string())

        print(f"[EMAIL SENT] To: {to_email} | Subject: {subject}")

    except smtplib.SMTPAuthenticationError:
        print(f"[EMAIL ERROR] Gmail authentication failed. Check MAIL_SENDER_EMAIL and MAIL_APP_PASSWORD.")
    except smtplib.SMTPException as e:
        print(f"[EMAIL ERROR] SMTP error sending to {to_email}: {e}")
    except Exception as e:
        print(f"[EMAIL ERROR] Unexpected error sending to {to_email}: {e}")

def generate_whatsapp_link(phone_number, text_content):
    """Generate WhatsApp Click-to-Chat URL."""
    clean_phone = ''.join(filter(str.isdigit, str(phone_number or '')))
    encoded_text = urllib.parse.quote(text_content)
    return f"https://wa.me/{clean_phone}?text={encoded_text}"

def smart_distribute_food(donation_id):
    """Automatically split food donation across nearby NGOs based on NGO capacity."""
    db = database.get_db()
    donation = db.execute('SELECT * FROM donations WHERE id = ?', (donation_id,)).fetchone()
    if not donation:
        return False, "Donation not found."

    total_servings = donation['servings_count'] or 0
    if total_servings <= 0:
        try:
            total_servings = int(''.join(filter(str.isdigit, donation['quantity'])))
        except ValueError:
            total_servings = 100

    matched_ngos = find_nearby_ngos(donation['latitude'], donation['longitude'])
    if not matched_ngos:
        return False, "No active online NGOs found within service radius."

    # Clear previous allocations for this donation if any
    db.execute('DELETE FROM donation_allocations WHERE donation_id = ?', (donation_id,))
    
    remaining = total_servings
    allocated_count = 0

    for item in matched_ngos:
        ngo = item['ngo']
        max_pickup = ngo['max_meals_per_pickup'] or 200
        avail_cap = item['available_capacity']
        
        alloc_amount = min(remaining, max_pickup, avail_cap)
        if alloc_amount > 0:
            db.execute('''
                INSERT INTO donation_allocations (donation_id, ngo_id, allocated_quantity, status)
                VALUES (?, ?, ?, 'Reserved')
            ''', (donation_id, ngo['id'], alloc_amount))
            
            # Update NGO current capacity used
            db.execute('UPDATE users SET current_capacity_used = current_capacity_used + ? WHERE id = ?',
                       (alloc_amount, ngo['id']))
            
            # In-App Notification
            create_notification(
                user_id=ngo['id'],
                title=f"Smart Match: {alloc_amount} Meals Allocated",
                message=f"You were auto-assigned {alloc_amount} meals from '{donation['food_name']}'!",
                link=f"/donations/{donation_id}",
                type_str='success'
            )

            # Email Dispatch
            email_body = f"Hello {ngo['name']},\n\nYou have been auto-matched with {alloc_amount} meals from a new donation!\n\nFood Item: {donation['food_name']}\nAllocated Quantity: {alloc_amount} Meals\nPickup Deadline: {donation['pickup_deadline']}\nLocation: {donation['location']}\nGoogle Maps: https://www.google.com/maps/search/?api=1&query={donation['latitude']},{donation['longitude']}\n\nLog in to confirm pickup."
            send_email_notification(ngo['email'], f"FoodBridge Auto-Match: {alloc_amount} Meals Reserved", email_body)

            remaining -= alloc_amount
            allocated_count += 1
            
        if remaining <= 0:
            break

    new_status = 'Reserved' if allocated_count > 0 else 'Available'
    db.execute('UPDATE donations SET status = ? WHERE id = ?', (new_status, donation_id))
    
    # Notify Donor
    create_notification(
        user_id=donation['donor_id'],
        title="Smart Food Splitting Completed",
        message=f"Your donation of {total_servings} meals was split & assigned across {allocated_count} nearby NGOs!",
        link=f"/donations/{donation_id}",
        type_str='info'
    )

    db.commit()
    if allocated_count > 0:
        return True, f"Successfully split & assigned food across {allocated_count} nearby NGOs!"
    else:
        return False, "Nearby NGOs exist, but none currently have remaining daily capacity."

# ----------------------------------------------------
# MAIN & AUTHENTICATION ROUTES
# ----------------------------------------------------

@app.route('/')
def index():
    """Homepage with statistics, impact numbers, live map preview, and recent food donations."""
    db = database.get_db()
    
    total_donations = db.execute('SELECT COUNT(*) as count FROM donations').fetchone()['count']
    available_count = db.execute("SELECT COUNT(*) as count FROM donations WHERE status = 'Available'").fetchone()['count']
    delivered_count = db.execute("SELECT COUNT(*) as count FROM donations WHERE status IN ('Delivered', 'Completed')").fetchone()['count']
    donor_count = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'donor'").fetchone()['count']
    ngo_count = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'ngo'").fetchone()['count']
    
    # Calculate Total Servings Rescued
    total_meals_row = db.execute("SELECT SUM(servings_count) as total FROM donations WHERE status IN ('Delivered', 'Completed', 'Picked Up', 'Reserved')").fetchone()
    total_meals_rescued = total_meals_row['total'] or 740
    food_waste_prevented_kg = round(total_meals_rescued * 0.3, 1)
    
    recent_donations = db.execute('''
        SELECT d.*, u.name as donor_name, u.organization as donor_org, u.phone as donor_phone
        FROM donations d
        JOIN users u ON d.donor_id = u.id
        WHERE d.status IN ('Available', 'Reserved')
        ORDER BY d.created_at DESC LIMIT 6
    ''').fetchall()
    
    stats = {
        'total_donations': total_donations,
        'available': available_count,
        'delivered': delivered_count,
        'donors': donor_count,
        'ngos': ngo_count,
        'total_meals_rescued': total_meals_rescued,
        'food_waste_prevented_kg': food_waste_prevented_kg
    }
    
    return render_template('index.html', stats=stats, recent_donations=recent_donations)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User Login Route."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        db = database.get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['user_role'] = user['role']
            session['user_organization'] = user['organization']
            
            flash(f"Welcome back, {user['name']} ({user['role'].upper()})!", 'success')
            next_page = request.args.get('next')
            if user['role'] == 'admin':
                return redirect(next_page or url_for('admin_dashboard'))
            return redirect(next_page or url_for('donations'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User Registration Route supporting Donor, NGO, and Admin roles."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'donor')
        phone = request.form.get('phone', '').strip()
        organization = request.form.get('organization', '').strip()
        
        # NGO specific fields
        max_meals = request.form.get('max_meals_per_pickup', 200)
        daily_cap = request.form.get('daily_capacity', 500)
        radius = request.form.get('service_radius_km', 10.0)
        
        if not name or not email or not password or role not in ['donor', 'ngo', 'admin']:
            flash('Please fill in all required fields.', 'warning')
            return render_template('register.html')
            
        db = database.get_db()
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            flash('An account with this email already exists.', 'danger')
            return render_template('register.html')
            
        password_hash = generate_password_hash(password)
        db.execute('''
            INSERT INTO users (name, email, password_hash, role, phone, organization, max_meals_per_pickup, daily_capacity, service_radius_km)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, email, password_hash, role, phone, organization, max_meals, daily_cap, radius))
        db.commit()
        
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['user_role'] = user['role']
        session['user_organization'] = user['organization']
        
        flash('Account registered successfully! Welcome to FoodBridge MVP 2.0.', 'success')
        return redirect(url_for('donations'))
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ----------------------------------------------------
# DONATION MANAGEMENT & SMART MATCHING ROUTES
# ----------------------------------------------------

@app.route('/donations')
def donations():
    """List food donations with card view, map view, Veg/Non-Veg filters, search, and status counters."""
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
    food_type_filter = request.args.get('type', 'all')
    search_query = request.args.get('q', '').strip()
    
    db = database.get_db()
    query = '''
        SELECT d.*, 
               u_donor.name as donor_name, u_donor.organization as donor_org, u_donor.phone as donor_phone,
               u_ngo.name as ngo_name, u_ngo.organization as ngo_org
        FROM donations d
        JOIN users u_donor ON d.donor_id = u_donor.id
        LEFT JOIN users u_ngo ON d.ngo_id = u_ngo.id
        WHERE 1=1
    '''
    params = []
    
    if status_filter != 'all':
        query += ' AND d.status = ?'
        params.append(status_filter)
        
    if category_filter != 'all':
        query += ' AND d.category = ?'
        params.append(category_filter)

    if food_type_filter != 'all':
        query += ' AND d.food_type = ?'
        params.append(food_type_filter)
        
    if search_query:
        query += ' AND (d.food_name LIKE ? OR d.location LIKE ? OR d.notes LIKE ?)'
        wildcard = f"%{search_query}%"
        params.extend([wildcard, wildcard, wildcard])
        
    query += ' ORDER BY d.created_at DESC'
    
    donation_list = db.execute(query, params).fetchall()
    
    counts = {
        'all': db.execute('SELECT COUNT(*) as c FROM donations').fetchone()['c'],
        'Available': db.execute("SELECT COUNT(*) as c FROM donations WHERE status='Available'").fetchone()['c'],
        'Reserved': db.execute("SELECT COUNT(*) as c FROM donations WHERE status='Reserved'").fetchone()['c'],
        'Picked Up': db.execute("SELECT COUNT(*) as c FROM donations WHERE status='Picked Up'").fetchone()['c'],
        'Delivered': db.execute("SELECT COUNT(*) as c FROM donations WHERE status IN ('Delivered', 'Completed')").fetchone()['c'],
    }
    
    return render_template('donations.html', 
                           donations=donation_list, 
                           selected_status=status_filter,
                           selected_category=category_filter,
                           selected_type=food_type_filter,
                           search_query=search_query,
                           counts=counts)

@app.route('/donations/new', methods=['GET', 'POST'])
@login_required
@donor_required
def add_donation():
    """Donor posts a new food donation with enhanced MVP 2.0 options."""
    if request.method == 'POST':
        food_name = request.form.get('food_name', '').strip()
        quantity = request.form.get('quantity', '').strip()
        food_type = request.form.get('food_type', 'Veg')
        servings_count = int(request.form.get('servings_count', 50))
        category = request.form.get('category', 'Prepared Meals')
        location = request.form.get('location', '').strip()
        pickup_deadline = request.form.get('pickup_deadline', '').strip()
        notes = request.form.get('notes', '').strip()
        special_instructions = request.form.get('special_instructions', '').strip()
        auto_split = 'auto_split' in request.form
        
        try:
            latitude = float(request.form.get('latitude', 12.9716))
            longitude = float(request.form.get('longitude', 77.5946))
        except ValueError:
            latitude, longitude = 12.9716, 77.5946
            
        # Image Upload Handling
        food_image = None
        if 'food_image' in request.files:
            file = request.files['food_image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"food_{int(time.time())}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                food_image = f"uploads/{filename}"

        if not food_name or not quantity or not location or not pickup_deadline:
            flash('Please fill in all required fields (Food Name, Quantity, Location, Pickup Deadline).', 'warning')
            return render_template('add_donation.html')
            
        db = database.get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO donations (donor_id, food_name, quantity, food_type, servings_count, category, location, latitude, longitude, pickup_deadline, notes, special_instructions, food_image, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Available')
        ''', (session['user_id'], food_name, quantity, food_type, servings_count, category, location, latitude, longitude, pickup_deadline, notes, special_instructions, food_image))
        donation_id = cursor.lastrowid
        db.commit()

        # Perform Nearby NGO Matching & Auto Split if checked or for large quantities
        matched_ngos = find_nearby_ngos(latitude, longitude)
        
        # Dispatch notifications to matched NGOs
        for m in matched_ngos:
            create_notification(
                user_id=m['ngo']['id'],
                title="New Nearby Food Donation!",
                message=f"New donation '{food_name}' ({servings_count} meals) available within {m['distance_km']} km!",
                link=f"/donations/{donation_id}",
                type_str='info'
            )

        if auto_split:
            success, msg = smart_distribute_food(donation_id)
            flash(f"Food donation listed! {msg}", 'success')
        else:
            flash(f"Food donation listed successfully! {len(matched_ngos)} nearby NGOs have been notified.", 'success')
            
        return redirect(url_for('donation_detail', donation_id=donation_id))
        
    return render_template('add_donation.html')

@app.route('/donations/<int:donation_id>')
def donation_detail(donation_id):
    """View details of a single food donation, including workflow timeline, split allocations, map, and proof photos."""
    db = database.get_db()
    donation = db.execute('''
        SELECT d.*, 
               u_donor.name as donor_name, u_donor.organization as donor_org, u_donor.phone as donor_phone, u_donor.email as donor_email,
               u_ngo.name as ngo_name, u_ngo.organization as ngo_org, u_ngo.phone as ngo_phone
        FROM donations d
        JOIN users u_donor ON d.donor_id = u_donor.id
        LEFT JOIN users u_ngo ON d.ngo_id = u_ngo.id
        WHERE d.id = ?
    ''', (donation_id,)).fetchone()
    
    if not donation:
        flash('Donation not found.', 'danger')
        return redirect(url_for('donations'))

    # Fetch split allocations if present
    allocations = db.execute('''
        SELECT da.*, u.name as ngo_name, u.organization as ngo_org, u.phone as ngo_phone
        FROM donation_allocations da
        JOIN users u ON da.ngo_id = u.id
        WHERE da.donation_id = ?
    ''', (donation_id,)).fetchall()

    # Find nearby NGOs
    nearby_ngos = find_nearby_ngos(donation['latitude'], donation['longitude'])

    # Build WhatsApp Share Link
    wa_message = f"🥦 *FoodBridge Alert*: Fresh Food Donation Available!\n\n*Item*: {donation['food_name']} ({donation['food_type']})\n*Quantity*: {donation['quantity']} ({donation['servings_count']} Servings)\n*Deadline*: {donation['pickup_deadline']}\n*Location*: {donation['location']}\n\nClick link to claim: {request.url_root}donations/{donation_id}"
    whatsapp_share_url = generate_whatsapp_link('', wa_message)

    return render_template('donation_detail.html', 
                           donation=donation, 
                           allocations=allocations,
                           nearby_ngos=nearby_ngos,
                           whatsapp_share_url=whatsapp_share_url)

@app.route('/donations/<int:donation_id>/smart-split', methods=['POST'])
@login_required
def trigger_smart_split(donation_id):
    """Manually trigger Smart Capacity Auto-Split algorithm for a donation."""
    success, msg = smart_distribute_food(donation_id)
    if success:
        flash(msg, 'success')
    else:
        flash(msg, 'warning')
    return redirect(url_for('donation_detail', donation_id=donation_id))

@app.route('/donations/<int:donation_id>/claim', methods=['POST'])
@login_required
@ngo_required
def claim_donation(donation_id):
    """NGO claims a full single food donation for pickup."""
    db = database.get_db()
    donation = db.execute('SELECT * FROM donations WHERE id = ?', (donation_id,)).fetchone()
    
    if not donation or donation['status'] != 'Available':
        flash('This food item is no longer available.', 'warning')
        return redirect(url_for('donation_detail', donation_id=donation_id))
        
    db.execute('''
        UPDATE donations 
        SET status = 'Reserved', ngo_id = ? 
        WHERE id = ?
    ''', (session['user_id'], donation_id))
    
    # Notify Donor
    create_notification(
        user_id=donation['donor_id'],
        title="Pickup Accepted!",
        message=f"{session['user_name']} has accepted pickup for '{donation['food_name']}'.",
        link=f"/donations/{donation_id}",
        type_str='success'
    )
    
    db.commit()
    flash('Pickup accepted! You are now assigned to collect this food donation.', 'success')
    return redirect(url_for('donation_detail', donation_id=donation_id))

@app.route('/donations/<int:donation_id>/status', methods=['POST'])
@login_required
def update_status(donation_id):
    """Update donation workflow status (Available -> Reserved -> Picked Up -> Delivered -> Completed)."""
    new_status = request.form.get('status')
    if new_status not in ['Available', 'Reserved', 'Picked Up', 'Delivered', 'Completed']:
        flash('Invalid status update.', 'danger')
        return redirect(url_for('donation_detail', donation_id=donation_id))
        
    db = database.get_db()
    donation = db.execute('SELECT * FROM donations WHERE id = ?', (donation_id,)).fetchone()
    
    if not donation:
        flash('Donation not found.', 'danger')
        return redirect(url_for('donations'))

    db.execute('UPDATE donations SET status = ? WHERE id = ?', (new_status, donation_id))
    
    # Also update allocation status if present
    db.execute('UPDATE donation_allocations SET status = ? WHERE donation_id = ?', (new_status, donation_id))
    
    db.commit()
    flash(f"Donation status updated to '{new_status}' successfully!", 'success')
    return redirect(url_for('donation_detail', donation_id=donation_id))

@app.route('/donations/<int:donation_id>/proof', methods=['POST'])
@login_required
def upload_proof(donation_id):
    """Upload photo proof for pickup or delivery with timestamp verification."""
    proof_type = request.form.get('proof_type', 'pickup') # 'pickup' or 'delivery'
    
    if 'proof_image' not in request.files:
        flash('No image file selected.', 'warning')
        return redirect(url_for('donation_detail', donation_id=donation_id))
        
    file = request.files['proof_image']
    if not file or file.filename == '' or not allowed_file(file.filename):
        flash('Please upload a valid image file (JPG, PNG, WEBP).', 'danger')
        return redirect(url_for('donation_detail', donation_id=donation_id))
        
    filename = secure_filename(f"proof_{proof_type}_{donation_id}_{int(time.time())}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    relative_path = f"uploads/{filename}"
    timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    db = database.get_db()
    if proof_type == 'pickup':
        db.execute('''
            UPDATE donations 
            SET pickup_proof_image = ?, pickup_timestamp = ?, status = 'Picked Up'
            WHERE id = ?
        ''', (relative_path, timestamp_str, donation_id))
        flash('Pickup proof photo uploaded and verified! Status updated to Picked Up.', 'success')
    else:
        db.execute('''
            UPDATE donations 
            SET delivery_proof_image = ?, delivery_timestamp = ?, status = 'Completed'
            WHERE id = ?
        ''', (relative_path, timestamp_str, donation_id))
        flash('Delivery proof photo uploaded and verified! Status updated to Completed.', 'success')
        
    db.commit()
    return redirect(url_for('donation_detail', donation_id=donation_id))

# ----------------------------------------------------
# NGO CAPACITY MANAGEMENT & DASHBOARDS
# ----------------------------------------------------

@app.route('/ngo/capacity', methods=['GET', 'POST'])
@login_required
@ngo_required
def ngo_capacity():
    """NGO configures maximum meals per pickup, daily capacity, availability (Online/Offline), radius, and location."""
    db = database.get_db()
    user_id = session['user_id']
    
    if request.method == 'POST':
        max_meals = int(request.form.get('max_meals_per_pickup', 200))
        daily_cap = int(request.form.get('daily_capacity', 500))
        availability = request.form.get('availability', 'Online')
        service_radius = float(request.form.get('service_radius_km', 10.0))
        latitude = float(request.form.get('latitude', 12.9716))
        longitude = float(request.form.get('longitude', 77.5946))
        reset_used = 'reset_used' in request.form
        
        query = '''
            UPDATE users 
            SET max_meals_per_pickup = ?, daily_capacity = ?, availability = ?, service_radius_km = ?, latitude = ?, longitude = ?
        '''
        params = [max_meals, daily_cap, availability, service_radius, latitude, longitude]
        
        if reset_used:
            query += ', current_capacity_used = 0'
            
        query += ' WHERE id = ?'
        params.append(user_id)
        
        db.execute(query, params)
        db.commit()
        
        flash('NGO Capacity Settings updated successfully!', 'success')
        return redirect(url_for('ngo_capacity'))
        
    ngo_info = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    return render_template('ngo_capacity.html', ngo=ngo_info)

@app.route('/dashboard')
@login_required
def dashboard():
    """Role-specific User Dashboard."""
    db = database.get_db()
    user_id = session['user_id']
    user_role = session['user_role']
    
    if user_role == 'admin':
        return redirect(url_for('admin_dashboard'))
        
    elif user_role == 'donor':
        my_donations = db.execute('''
            SELECT d.*, u_ngo.name as ngo_name, u_ngo.organization as ngo_org
            FROM donations d
            LEFT JOIN users u_ngo ON d.ngo_id = u_ngo.id
            WHERE d.donor_id = ?
            ORDER BY d.created_at DESC
        ''', (user_id,)).fetchall()
        
        total_servings = sum(d['servings_count'] for d in my_donations if d['servings_count'])
        stats = {
            'total_posted': len(my_donations),
            'available': sum(1 for d in my_donations if d['status'] == 'Available'),
            'picked': sum(1 for d in my_donations if d['status'] == 'Picked Up'),
            'delivered': sum(1 for d in my_donations if d['status'] in ['Delivered', 'Completed']),
            'total_servings_saved': total_servings
        }
        return render_template('dashboard.html', donations=my_donations, stats=stats)
        
    else: # NGO role
        # Fetch directly assigned donations OR split allocations assigned to this NGO
        my_allocations = db.execute('''
            SELECT da.*, d.food_name, d.food_type, d.quantity, d.location, d.pickup_deadline, d.latitude, d.longitude,
                   u_donor.name as donor_name, u_donor.organization as donor_org, u_donor.phone as donor_phone
            FROM donation_allocations da
            JOIN donations d ON da.donation_id = d.id
            JOIN users u_donor ON d.donor_id = u_donor.id
            WHERE da.ngo_id = ?
            ORDER BY da.created_at DESC
        ''', (user_id,)).fetchall()

        my_single_pickups = db.execute('''
            SELECT d.*, u_donor.name as donor_name, u_donor.organization as donor_org, u_donor.phone as donor_phone
            FROM donations d
            JOIN users u_donor ON d.donor_id = u_donor.id
            WHERE d.ngo_id = ?
            ORDER BY d.created_at DESC
        ''', (user_id,)).fetchall()
        
        ngo_info = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        
        stats = {
            'total_claimed': len(my_allocations) + len(my_single_pickups),
            'active_pickups': sum(1 for a in my_allocations if a['status'] == 'Reserved') + sum(1 for d in my_single_pickups if d['status'] == 'Reserved'),
            'completed_deliveries': sum(1 for a in my_allocations if a['status'] in ['Delivered', 'Completed']) + sum(1 for d in my_single_pickups if d['status'] in ['Delivered', 'Completed']),
            'daily_capacity': ngo_info['daily_capacity'] or 500,
            'capacity_used': ngo_info['current_capacity_used'] or 0
        }
        return render_template('dashboard.html', allocations=my_allocations, single_pickups=my_single_pickups, stats=stats, ngo=ngo_info)

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    """Comprehensive Admin Dashboard with system analytics, waste metrics, and NGO performance leaderboard."""
    db = database.get_db()
    
    total_donations = db.execute('SELECT COUNT(*) as c FROM donations').fetchone()['c']
    total_donors = db.execute("SELECT COUNT(*) as c FROM users WHERE role = 'donor'").fetchone()['c']
    total_ngos = db.execute("SELECT COUNT(*) as c FROM users WHERE role = 'ngo'").fetchone()['c']
    active_pickups = db.execute("SELECT COUNT(*) as c FROM donations WHERE status IN ('Reserved', 'Picked Up')").fetchone()['c']
    completed_deliveries = db.execute("SELECT COUNT(*) as c FROM donations WHERE status IN ('Delivered', 'Completed')").fetchone()['c']
    
    total_servings = db.execute("SELECT SUM(servings_count) as total FROM donations").fetchone()['total'] or 760
    food_waste_prevented_kg = round(total_servings * 0.3, 1)

    # NGO Performance & Reliability Scoring
    ngos = db.execute("SELECT * FROM users WHERE role = 'ngo'").fetchall()
    ngo_performance = []
    for n in ngos:
        # Count allocations/pickups completed by this NGO
        completed_count = db.execute(
            "SELECT COUNT(*) as c FROM donation_allocations WHERE ngo_id = ? AND status IN ('Delivered', 'Completed')",
            (n['id'],)
        ).fetchone()['c']
        
        meals_collected = db.execute(
            "SELECT SUM(allocated_quantity) as total FROM donation_allocations WHERE ngo_id = ? AND status IN ('Delivered', 'Completed')",
            (n['id'],)
        ).fetchone()['total'] or (n['current_capacity_used'] or 0)
        
        # Calculate Reliability Score (0 - 100%)
        reliability_score = min(100, max(50, 75 + (completed_count * 5)))
        
        ngo_performance.append({
            'ngo': n,
            'completed_pickups': completed_count,
            'meals_collected': meals_collected,
            'reliability_score': reliability_score
        })

    all_users = db.execute("SELECT id, name, email, role, organization, phone, created_at FROM users ORDER BY created_at DESC").fetchall()

    stats = {
        'total_donations': total_donations,
        'total_donors': total_donors,
        'total_ngos': total_ngos,
        'active_pickups': active_pickups,
        'completed_deliveries': completed_deliveries,
        'total_servings': total_servings,
        'food_waste_prevented_kg': food_waste_prevented_kg
    }

    return render_template('admin_dashboard.html', stats=stats, ngo_performance=ngo_performance, users=all_users)

# ----------------------------------------------------
# NOTIFICATION CENTER & REST API ENDPOINTS
# ----------------------------------------------------

@app.route('/notifications')
@login_required
def notifications_view():
    """User Notification Center view."""
    db = database.get_db()
    notifs = db.execute('''
        SELECT * FROM notifications 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (session['user_id'],)).fetchall()
    
    # Mark all as read when opening notification center
    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
    db.commit()
    
    return render_template('notifications.html', notifications=notifs)

@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_read_notifications():
    db = database.get_db()
    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/donations')
def api_donations():
    """Return JSON format of all food donations for Leaflet map integration."""
    db = database.get_db()
    items = db.execute('''
        SELECT d.id, d.food_name, d.quantity, d.food_type, d.servings_count, d.category, d.location, d.latitude, d.longitude, d.pickup_deadline, d.status, d.is_urgent,
               u.name as donor_name, u.organization as donor_org
        FROM donations d
        JOIN users u ON d.donor_id = u.id
    ''').fetchall()
    return jsonify(items)

@app.route('/api/map-data')
def api_map_data():
    """Return both Donors and NGOs coordinates for live dual-layer Google / Leaflet maps."""
    db = database.get_db()
    donations_data = db.execute('''
        SELECT d.id, d.food_name, d.quantity, d.food_type, d.servings_count, d.location, d.latitude, d.longitude, d.status,
               u.name as donor_name
        FROM donations d
        JOIN users u ON d.donor_id = u.id
    ''').fetchall()
    
    ngos_data = db.execute('''
        SELECT id, name, organization, availability, service_radius_km, daily_capacity, current_capacity_used, latitude, longitude
        FROM users WHERE role = 'ngo'
    ''').fetchall()
    
    return jsonify({
        'donations': donations_data,
        'ngos': ngos_data
    })

# Admin: Force reset all NGO daily capacity counters manually
@app.route('/admin/reset-capacities', methods=['POST'])
@login_required
@admin_required
def admin_force_reset_capacities():
    """Admin can manually force a daily capacity reset for all NGOs."""
    today = datetime.now().strftime('%Y-%m-%d')
    db = database.get_db()
    affected = db.execute(
        "UPDATE users SET current_capacity_used = 0, capacity_reset_date = ? WHERE role = 'ngo'",
        (today,)
    ).rowcount
    db.commit()
    flash(f'Daily capacity counter reset for all {affected} NGOs successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

# Auto-initialize database if missing
if not os.path.exists(database.DATABASE):
    from init_db import seed_database
    seed_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting FoodBridge MVP 2.0 Server on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
