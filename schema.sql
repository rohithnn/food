DROP TABLE IF EXISTS donations;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('donor', 'ngo')),
    phone TEXT,
    organization TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id INTEGER NOT NULL,
    food_name TEXT NOT NULL,
    quantity TEXT NOT NULL,
    category TEXT DEFAULT 'Prepared Meals',
    location TEXT NOT NULL,
    latitude REAL DEFAULT 12.9716,
    longitude REAL DEFAULT 77.5946,
    expiry_time TEXT NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'Available' CHECK(status IN ('Available', 'Picked', 'Delivered')),
    ngo_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES users (id),
    FOREIGN KEY (ngo_id) REFERENCES users (id)
);
