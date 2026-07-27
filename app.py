import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import database

app = Flask(__name__)
app.secret_key = 'foodbridge_super_secret_key_change_in_production'

# Register teardown function to close DB connections
app.teardown_appcontext(database.close_connection)

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

def donor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'donor':
            flash('This action is restricted to Food Donors.', 'danger')
            return redirect(url_for('donations'))
        return f(*args, **kwargs)
    return decorated_function

def ngo_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'ngo':
            flash('This action is restricted to NGOs and Volunteers.', 'danger')
            return redirect(url_for('donations'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    """Make current user info available in all HTML templates."""
    return dict(
        current_user={
            'id': session.get('user_id'),
            'name': session.get('user_name'),
            'email': session.get('user_email'),
            'role': session.get('user_role'),
            'organization': session.get('user_organization')
        } if 'user_id' in session else None
    )

# ----------------------------------------------------
# MAIN & AUTHENTICATION ROUTES
# ----------------------------------------------------

@app.route('/')
def index():
    """Homepage with statistics and quick overview of active food donations."""
    db = database.get_db()
    
    # Calculate Impact Metrics
    total_donations = db.execute('SELECT COUNT(*) as count FROM donations').fetchone()['count']
    available_count = db.execute("SELECT COUNT(*) as count FROM donations WHERE status = 'Available'").fetchone()['count']
    delivered_count = db.execute("SELECT COUNT(*) as count FROM donations WHERE status = 'Delivered'").fetchone()['count']
    donor_count = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'donor'").fetchone()['count']
    ngo_count = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'ngo'").fetchone()['count']
    
    # Recent available food items
    recent_donations = db.execute('''
        SELECT d.*, u.name as donor_name, u.organization as donor_org, u.phone as donor_phone
        FROM donations d
        JOIN users u ON d.donor_id = u.id
        WHERE d.status = 'Available'
        ORDER BY d.created_at DESC LIMIT 6
    ''').fetchall()
    
    stats = {
        'total_donations': total_donations,
        'available': available_count,
        'delivered': delivered_count,
        'donors': donor_count,
        'ngos': ngo_count
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
            
            flash(f"Welcome back, {user['name']}!", 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('donations'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User Registration Route for Donors & NGOs."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'donor')
        phone = request.form.get('phone', '').strip()
        organization = request.form.get('organization', '').strip()
        
        if not name or not email or not password or role not in ['donor', 'ngo']:
            flash('Please fill in all required fields.', 'warning')
            return render_template('register.html')
            
        db = database.get_db()
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            flash('An account with this email already exists.', 'danger')
            return render_template('register.html')
            
        password_hash = generate_password_hash(password)
        db.execute('''
            INSERT INTO users (name, email, password_hash, role, phone, organization)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, email, password_hash, role, phone, organization))
        db.commit()
        
        # Retrieve newly created user to log in
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['user_role'] = user['role']
        session['user_organization'] = user['organization']
        
        flash('Account registered successfully! Welcome to FoodBridge.', 'success')
        return redirect(url_for('donations'))
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    """Clear session and log out."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ----------------------------------------------------
# DONATION MANAGEMENT ROUTES
# ----------------------------------------------------

@app.route('/donations')
def donations():
    """List all food donations with card layout, filters, search, and map view."""
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
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
        
    if search_query:
        query += ' AND (d.food_name LIKE ? OR d.location LIKE ? OR d.notes LIKE ?)'
        wildcard = f"%{search_query}%"
        params.extend([wildcard, wildcard, wildcard])
        
    query += ' ORDER BY d.created_at DESC'
    
    donation_list = db.execute(query, params).fetchall()
    
    # Get count by status for tab counters
    counts = {
        'all': db.execute('SELECT COUNT(*) as c FROM donations').fetchone()['c'],
        'Available': db.execute("SELECT COUNT(*) as c FROM donations WHERE status='Available'").fetchone()['c'],
        'Picked': db.execute("SELECT COUNT(*) as c FROM donations WHERE status='Picked'").fetchone()['c'],
        'Delivered': db.execute("SELECT COUNT(*) as c FROM donations WHERE status='Delivered'").fetchone()['c'],
    }
    
    return render_template('donations.html', 
                           donations=donation_list, 
                           selected_status=status_filter,
                           selected_category=category_filter,
                           search_query=search_query,
                           counts=counts)

@app.route('/donations/new', methods=['GET', 'POST'])
@login_required
@donor_required
def add_donation():
    """Route for Donors to post new food donations with location selection."""
    if request.method == 'POST':
        food_name = request.form.get('food_name', '').strip()
        quantity = request.form.get('quantity', '').strip()
        category = request.form.get('category', 'Prepared Meals')
        location = request.form.get('location', '').strip()
        expiry_time = request.form.get('expiry_time', '').strip()
        notes = request.form.get('notes', '').strip()
        
        try:
            latitude = float(request.form.get('latitude', 12.9716))
            longitude = float(request.form.get('longitude', 77.5946))
        except ValueError:
            latitude, longitude = 12.9716, 77.5946
            
        if not food_name or not quantity or not location or not expiry_time:
            flash('Please fill in all required fields (Food Name, Quantity, Location, Expiry Time).', 'warning')
            return render_template('add_donation.html')
            
        db = database.get_db()
        db.execute('''
            INSERT INTO donations (donor_id, food_name, quantity, category, location, latitude, longitude, expiry_time, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Available')
        ''', (session['user_id'], food_name, quantity, category, location, latitude, longitude, expiry_time, notes))
        db.commit()
        
        flash('Food donation successfully listed! NGOs can now view and claim pickup.', 'success')
        return redirect(url_for('donations'))
        
    return render_template('add_donation.html')

@app.route('/donations/<int:donation_id>')
def donation_detail(donation_id):
    """View details of a single food donation."""
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
        
    return render_template('donation_detail.html', donation=donation)

@app.route('/donations/<int:donation_id>/claim', methods=['POST'])
@login_required
@ngo_required
def claim_donation(donation_id):
    """NGO accepts/claims a food donation for pickup."""
    db = database.get_db()
    donation = db.execute('SELECT * FROM donations WHERE id = ?', (donation_id,)).fetchone()
    
    if not donation:
        flash('Donation not found.', 'danger')
        return redirect(url_for('donations'))
        
    if donation['status'] != 'Available':
        flash('This food item has already been claimed or processed.', 'warning')
        return redirect(url_for('donation_detail', donation_id=donation_id))
        
    db.execute('''
        UPDATE donations 
        SET status = 'Picked', ngo_id = ? 
        WHERE id = ?
    ''', (session['user_id'], donation_id))
    db.commit()
    
    flash('Pickup accepted! You are now assigned to pick up this donation.', 'success')
    return redirect(url_for('donation_detail', donation_id=donation_id))

@app.route('/donations/<int:donation_id>/status', methods=['POST'])
@login_required
def update_status(donation_id):
    """Update donation status (Picked or Delivered)."""
    new_status = request.form.get('status')
    if new_status not in ['Picked', 'Delivered', 'Available']:
        flash('Invalid status update.', 'danger')
        return redirect(url_for('donation_detail', donation_id=donation_id))
        
    db = database.get_db()
    donation = db.execute('SELECT * FROM donations WHERE id = ?', (donation_id,)).fetchone()
    
    if not donation:
        flash('Donation not found.', 'danger')
        return redirect(url_for('donations'))
        
    # Check permissions: donor who created or NGO who claimed can update
    is_owner_donor = (session.get('user_role') == 'donor' and donation['donor_id'] == session.get('user_id'))
    is_assigned_ngo = (session.get('user_role') == 'ngo' and (donation['ngo_id'] == session.get('user_id') or donation['ngo_id'] is None))
    
    if not (is_owner_donor or is_assigned_ngo):
        flash('You do not have permission to update this donation.', 'danger')
        return redirect(url_for('donation_detail', donation_id=donation_id))
        
    db.execute('UPDATE donations SET status = ? WHERE id = ?', (new_status, donation_id))
    db.commit()
    
    flash(f"Status updated to '{new_status}' successfully!", 'success')
    return redirect(url_for('donation_detail', donation_id=donation_id))

@app.route('/donations/<int:donation_id>/delete', methods=['POST'])
@login_required
@donor_required
def delete_donation(donation_id):
    """Donor cancels/deletes an available donation listing."""
    db = database.get_db()
    donation = db.execute('SELECT * FROM donations WHERE id = ?', (donation_id,)).fetchone()
    
    if not donation:
        flash('Donation not found.', 'danger')
        return redirect(url_for('donations'))
        
    if donation['donor_id'] != session['user_id']:
        flash('You can only delete your own donations.', 'danger')
        return redirect(url_for('donations'))
        
    db.execute('DELETE FROM donations WHERE id = ?', (donation_id,))
    db.commit()
    
    flash('Donation listing removed.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    """User Dashboard - showing relevant donations for current user."""
    db = database.get_db()
    user_id = session['user_id']
    user_role = session['user_role']
    
    if user_role == 'donor':
        # Donors see donations they posted
        my_donations = db.execute('''
            SELECT d.*, u_ngo.name as ngo_name, u_ngo.organization as ngo_org
            FROM donations d
            LEFT JOIN users u_ngo ON d.ngo_id = u_ngo.id
            WHERE d.donor_id = ?
            ORDER BY d.created_at DESC
        ''', (user_id,)).fetchall()
        
        stats = {
            'total_posted': len(my_donations),
            'available': sum(1 for d in my_donations if d['status'] == 'Available'),
            'picked': sum(1 for d in my_donations if d['status'] == 'Picked'),
            'delivered': sum(1 for d in my_donations if d['status'] == 'Delivered')
        }
        return render_template('dashboard.html', donations=my_donations, stats=stats)
        
    else: # NGO role
        # NGOs see pickups they accepted/claimed
        my_pickups = db.execute('''
            SELECT d.*, u_donor.name as donor_name, u_donor.organization as donor_org, u_donor.phone as donor_phone
            FROM donations d
            JOIN users u_donor ON d.donor_id = u_donor.id
            WHERE d.ngo_id = ?
            ORDER BY d.created_at DESC
        ''', (user_id,)).fetchall()
        
        stats = {
            'total_claimed': len(my_pickups),
            'active_pickups': sum(1 for d in my_pickups if d['status'] == 'Picked'),
            'completed_deliveries': sum(1 for d in my_pickups if d['status'] == 'Delivered')
        }
        return render_template('dashboard.html', donations=my_pickups, stats=stats)

# ----------------------------------------------------
# REST API ENDPOINTS FOR MAPS & DYNAMIC UPDATES
# ----------------------------------------------------

@app.route('/api/donations')
def api_donations():
    """Return JSON list of food donations for Leaflet map initialization."""
    db = database.get_db()
    items = db.execute('''
        SELECT d.id, d.food_name, d.quantity, d.category, d.location, d.latitude, d.longitude, d.expiry_time, d.status,
               u.name as donor_name, u.organization as donor_org
        FROM donations d
        JOIN users u ON d.donor_id = u.id
    ''').fetchall()
    return jsonify(items)

if __name__ == '__main__':
    # Initialize DB if not created yet
    if not os.path.exists(database.DATABASE):
        from init_db import seed_database
        seed_database()
        
    print("Starting FoodBridge Flask Server on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
