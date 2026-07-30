DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS donation_allocations;
DROP TABLE IF EXISTS donations;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('donor', 'ngo', 'admin')),
    phone TEXT,
    organization TEXT,
    -- NGO Capacity & Location Configuration
    max_meals_per_pickup INTEGER DEFAULT 200,
    daily_capacity INTEGER DEFAULT 500,
    current_capacity_used INTEGER DEFAULT 0,
    capacity_reset_date TEXT DEFAULT '',
    availability TEXT DEFAULT 'Online' CHECK(availability IN ('Online', 'Offline')),
    service_radius_km REAL DEFAULT 10.0,
    latitude REAL DEFAULT 12.9716,
    longitude REAL DEFAULT 77.5946,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id INTEGER NOT NULL,
    food_name TEXT NOT NULL,
    quantity TEXT NOT NULL,
    food_type TEXT DEFAULT 'Veg' CHECK(food_type IN ('Veg', 'Non-Veg')),
    servings_count INTEGER DEFAULT 50,
    category TEXT DEFAULT 'Prepared Meals',
    location TEXT NOT NULL,
    latitude REAL DEFAULT 12.9716,
    longitude REAL DEFAULT 77.5946,
    pickup_deadline TEXT NOT NULL,
    notes TEXT,
    special_instructions TEXT,
    food_image TEXT,
    status TEXT NOT NULL DEFAULT 'Available' CHECK(status IN ('Available', 'Reserved', 'Picked Up', 'Delivered', 'Completed')),
    ngo_id INTEGER,
    pickup_proof_image TEXT,
    pickup_timestamp TEXT,
    delivery_proof_image TEXT,
    delivery_timestamp TEXT,
    is_urgent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES users (id),
    FOREIGN KEY (ngo_id) REFERENCES users (id)
);

CREATE TABLE donation_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donation_id INTEGER NOT NULL,
    ngo_id INTEGER NOT NULL,
    allocated_quantity INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'Reserved' CHECK(status IN ('Reserved', 'Picked Up', 'Delivered', 'Completed')),
    pickup_proof_image TEXT,
    pickup_timestamp TEXT,
    delivery_proof_image TEXT,
    delivery_timestamp TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donation_id) REFERENCES donations (id) ON DELETE CASCADE,
    FOREIGN KEY (ngo_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    link TEXT,
    type TEXT DEFAULT 'info',
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
