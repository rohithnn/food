import sqlite3
import os
from werkzeug.security import generate_password_hash
from database import DATABASE, init_db

def seed_database():
    """Seed database with realistic initial users, NGOs, Admin, food donations, smart allocations, and notifications."""
    init_db()
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    default_password = generate_password_hash('password123')
    
    # 1. Create Sample Users (Admin, Donors, NGOs)
    users = [
        # (name, email, password_hash, role, phone, organization, max_meals, daily_cap, cap_used, avail, radius, lat, lng)
        ('Platform Admin', 'admin@foodbridge.org', default_password, 'admin', '+1 555-0000', 'FoodBridge HQ', 0, 0, 0, 'Online', 0.0, 12.9716, 77.5946),
        ('Grand Palace Hotel', 'donor@grandhotel.com', default_password, 'donor', '+1 555-0192', 'Grand Palace Hospitality', 0, 0, 0, 'Online', 0.0, 12.9716, 77.5946),
        ('Royal Banquet Services', 'events@royalbanquet.com', default_password, 'donor', '+1 555-0184', 'Royal Banquets & Events', 0, 0, 0, 'Online', 0.0, 12.9654, 77.6012),
        ('Metro Catering Corp', 'info@metrocatering.com', default_password, 'donor', '+1 555-0199', 'Metro Events', 0, 0, 0, 'Online', 0.0, 12.9750, 77.5980),
        
        # NGOs with Location & Capacity
        ('FoodCare Foundation', 'ngo@foodcare.org', default_password, 'ngo', '+1 555-0144', 'FoodCare Welfare Trust', 200, 500, 150, 'Online', 15.0, 12.9720, 77.5950),
        ('Hope Shelter Volunteer', 'volunteer@hopehouse.org', default_password, 'ngo', '+1 555-0177', 'Hope Community Shelter', 150, 300, 100, 'Online', 10.0, 12.9650, 77.6010),
        ('City Feast Outreach', 'contact@cityfeast.org', default_password, 'ngo', '+1 555-0211', 'City Feast NGO', 300, 600, 250, 'Online', 20.0, 12.9800, 77.5900)
    ]
    
    cursor.executemany('''
        INSERT INTO users (name, email, password_hash, role, phone, organization, max_meals_per_pickup, daily_capacity, current_capacity_used, availability, service_radius_km, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', users)
    
    # 2. Create Sample Food Donations
    donations = [
        (
            2, # donor_id (Grand Palace Hotel)
            'Surplus Banquet Feast (Biryani & Gravy)',
            '500 Meals (~150 kg)',
            'Non-Veg',
            500,
            'Prepared Meals',
            'MG Road Grand Hotel, Central City',
            12.9716, 77.5946,
            'Today, 10:30 PM (Urgent Pickup)',
            'Packed in food-grade insulated thermal boxes. High quality surplus food from evening wedding banquet.',
            'Use service elevator at rear loading dock. Call manager upon arrival.',
            None, # food_image
            'Reserved', # status
            None, # ngo_id
            1 # is_urgent
        ),
        (
            3, # donor_id (Royal Banquet Services)
            'Fresh Artisan Bread Rolls & Pastries',
            '120 Portions (~30 kg)',
            'Veg',
            120,
            'Bakery Items',
            '45 Residency Road Banquet Hall',
            12.9654, 77.6012,
            'Tomorrow, 12:00 PM',
            'Baked fresh today for corporate event. Untouched excess items.',
            'Ask for Chef Rajesh at reception desk.',
            None,
            'Available',
            None,
            0
        ),
        (
            2, # donor_id (Grand Palace Hotel)
            'Assorted Fresh Fruit Baskets',
            '60 Portions (~25 kg)',
            'Veg',
            60,
            'Fresh Produce',
            'MG Road Grand Hotel, Central City',
            12.9716, 77.5946,
            'Today, 09:00 PM',
            'Apples, bananas, and oranges. High nutritional value.',
            'Deliveries can pick up from lobby desk.',
            None,
            'Delivered',
            5, # FoodCare Foundation
            0
        ),
        (
            4, # donor_id (Metro Catering Corp)
            'Paneer Butter Masala & Naan Breads',
            '80 Meals (~25 kg)',
            'Veg',
            80,
            'Prepared Meals',
            '78 Indiranagar Main Road',
            12.9784, 77.6408,
            'Today, 11:00 PM',
            'Vegetarian feast untouched from corporate luncheon.',
            'Contact supervisor Anita at gate 2.',
            None,
            'Available',
            None,
            0
        )
    ]
    
    cursor.executemany('''
        INSERT INTO donations (donor_id, food_name, quantity, food_type, servings_count, category, location, latitude, longitude, pickup_deadline, notes, special_instructions, food_image, status, ngo_id, is_urgent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', donations)
    
    # 3. Create Smart Split Allocations for Donation 1 (500 Meals split among 3 NGOs)
    # Donation ID 1 -> NGO 5 (150 meals), NGO 6 (100 meals), NGO 7 (250 meals)
    allocations = [
        (1, 5, 150, 'Reserved'), # FoodCare Foundation
        (1, 6, 100, 'Reserved'), # Hope Shelter Volunteer
        (1, 7, 250, 'Reserved')  # City Feast Outreach
    ]
    
    cursor.executemany('''
        INSERT INTO donation_allocations (donation_id, ngo_id, allocated_quantity, status)
        VALUES (?, ?, ?, ?)
    ''', allocations)
    
    # 4. Create Initial Notifications
    notifications = [
        (1, 'System Initialized', 'FoodBridge MVP 2.0 automation engine active.', '/admin/dashboard', 'info', 0),
        (5, 'Smart Match: 150 Meals Allocated', 'Grand Palace Hotel posted 500 meals! You have been auto-assigned 150 meals based on your capacity.', '/donations/1', 'success', 0),
        (6, 'Smart Match: 100 Meals Allocated', 'Grand Palace Hotel posted 500 meals! You have been auto-assigned 100 meals based on your capacity.', '/donations/1', 'success', 0),
        (7, 'Smart Match: 250 Meals Allocated', 'Grand Palace Hotel posted 500 meals! You have been auto-assigned 250 meals based on your capacity.', '/donations/1', 'success', 0),
        (2, 'Split Distribution Complete', 'Your 500 meals donation has been automatically matched & split across 3 nearby NGOs!', '/donations/1', 'info', 0)
    ]
    
    cursor.executemany('''
        INSERT INTO notifications (user_id, title, message, link, type, is_read)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', notifications)
    
    conn.commit()
    conn.close()
    print("Database successfully seeded with MVP 2.0 demo data!")

if __name__ == '__main__':
    seed_database()
