import sqlite3
import os
from werkzeug.security import generate_password_hash
from database import DATABASE, init_db

def seed_database():
    """Seed database with realistic initial users and food donations."""
    init_db()
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # 1. Create Sample Users
    default_password = generate_password_hash('password123')
    
    users = [
        ('Grand Palace Hotel', 'donor@grandhotel.com', default_password, 'donor', '+1 555-0192', 'Grand Palace Hospitality'),
        ('Royal Banquet Services', 'events@royalbanquet.com', default_password, 'donor', '+1 555-0184', 'Royal Banquets & Events'),
        ('FoodCare Foundation', 'ngo@foodcare.org', default_password, 'ngo', '+1 555-0144', 'FoodCare Welfare Trust'),
        ('Hope Shelter Volunteer', 'volunteer@hopehouse.org', default_password, 'ngo', '+1 555-0177', 'Hope Community Shelter')
    ]
    
    cursor.executemany('''
        INSERT INTO users (name, email, password_hash, role, phone, organization)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', users)
    
    # 2. Create Sample Food Donations
    # Expiry formatted for easy viewing
    donations = [
        (
            1, # donor_id (Grand Palace Hotel)
            'Surplus Buffet Rice & Veggie Curry',
            '50 Portions (approx. 20kg)',
            'Prepared Meals',
            'MG Road Grand Hotel, Central City',
            12.9716, 77.5946,
            'Today, 10:30 PM (Freshly prepared)',
            'Packed in food-grade insulated containers. Ready for immediate dispatch.',
            'Available',
            None
        ),
        (
            2, # donor_id (Royal Banquet Services)
            'Fresh Artisan Bread Rolls & Pastries',
            '120 Pieces',
            'Bakery Items',
            '45 Residency Road Banquet Hall',
            12.9654, 77.6012,
            'Tomorrow, 12:00 PM',
            'Baked fresh this morning for corporate breakfast event. Untouched excess.',
            'Available',
            None
        ),
        (
            1, # donor_id (Grand Palace Hotel)
            'Assorted Fresh Fruit Baskets',
            '15 Baskets (~30kg)',
            'Fresh Produce',
            'MG Road Grand Hotel, Central City',
            12.9716, 77.5946,
            'Today, 09:00 PM',
            'Apples, bananas, and oranges. High nutritional value.',
            'Picked',
            3 # NGO: FoodCare Foundation
        ),
        (
            2, # donor_id (Royal Banquet Services)
            'Paneer Butter Masala & Naan Breads',
            '35 Portions',
            'Prepared Meals',
            '45 Residency Road Banquet Hall',
            12.9654, 77.6012,
            'Yesterday, 11:00 PM',
            'Delivered safely to Hope Community Shelter dining hall.',
            'Delivered',
            4 # NGO: Hope Shelter Volunteer
        )
    ]
    
    cursor.executemany('''
        INSERT INTO donations (donor_id, food_name, quantity, category, location, latitude, longitude, expiry_time, notes, status, ngo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', donations)
    
    conn.commit()
    conn.close()
    print("Database successfully seeded with demo Donors, NGOs, and Food Donations!")

if __name__ == '__main__':
    seed_database()
