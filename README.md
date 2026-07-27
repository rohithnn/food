# 🌱 FoodBridge - Zero Food Waste Platform

> A full-stack web application connecting food donors (hotels, banquet halls, restaurants, event organizers) with local NGOs and volunteers to reduce food waste and nourish communities.

---

## 📋 Table of Contents
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Folder Structure](#-project-folder-structure)
- [Getting Started](#-getting-started)
- [Demo Accounts](#-demo-accounts)
- [Database Schema](#-database-schema)
- [API Endpoints](#-api-endpoints)

---

## ✨ Features

1. **Role-Based Authentication**:
   - **Donors**: Post excess food with quantity, category, pickup address, expiry time, packaging notes, and GPS coordinates. Manage active postings.
   - **NGOs & Volunteers**: Browse live listings, claim/accept food pickups, and transition donation statuses.

2. **Interactive Map Integration (Leaflet.js & OpenStreetMap)**:
   - **Location Picker**: Donors can click or drag a pin on an interactive map when listing food to auto-capture exact coordinates.
   - **Interactive Map View**: NGOs can switch from card layout to map view to visually locate available food donations in their area.
   - **Google Maps Navigation**: 1-click links for turn-by-turn directions.

3. **Real-time Status Tracking**:
   - Status workflow: `Available` ➔ `Picked Up` ➔ `Delivered`
   - Visual progress timeline bar on donation details.

4. **Directory Search & Category Filters**:
   - Filter by status tabs (*All*, *Available*, *Picked*, *Delivered*).
   - Search by food item, location, or donor name.

5. **Modern, Responsive UI**:
   - Glassmorphism sticky navbar, responsive card grid, status pulse badges, dark hero banner, and mobile-friendly controls.

---

## 🛠️ Tech Stack

- **Backend**: Python 3, Flask framework
- **Database**: SQLite 3
- **Frontend**: HTML5, Vanilla CSS3 (Custom Design System with CSS Variables), JavaScript (ES6+)
- **Mapping**: Leaflet.js with OpenStreetMap tiles (Zero API key dependencies)
- **Security**: Werkzeug password hashing, session-based authorization

---

## 📂 Project Folder Structure

```text
food/
├── app.py                   # Main Flask application & routing logic
├── database.py              # SQLite connection manager & helper functions
├── schema.sql               # Database table structure (users, donations)
├── init_db.py               # Database setup and seed data script
├── foodbridge.db            # SQLite database file (created on init)
├── README.md                # Project documentation
├── templates/               # Jinja2 HTML Templates
│   ├── base.html            # Layout master template with navbar & footer
│   ├── index.html           # Landing page with stats & active food feed
│   ├── login.html           # Login page with demo account fill buttons
│   ├── register.html        # Register page with Donor/NGO role choice
│   ├── donations.html       # Food directory with card/map view toggle & search
│   ├── add_donation.html    # Donation form with interactive map picker
│   ├── donation_detail.html # Detail page with status timeline & map
│   └── dashboard.html       # User activity dashboard
└── static/
    ├── css/
    │   └── style.css        # Complete CSS design system & responsive styling
    └── js/
        └── main.js         # Leaflet map handlers & interactive UI scripts
```

---

## 🚀 Getting Started

### Prerequisites
Make sure you have Python 3.8+ installed on your machine.

### 1. Clone or Download Repository
Navigate to the project directory:
```bash
cd d:\rohith\project\food
```

### 2. Install Flask & Werkzeug (If not already installed)
```bash
pip install flask werkzeug
```

### 3. Initialize the Database & Seed Demo Data
Run the initializer script to create `foodbridge.db` and insert sample users & donations:
```bash
python init_db.py
```

### 4. Run the Application Server
Start the Flask development server:
```bash
python app.py
```

### 5. Access in Web Browser
Open your browser and visit:
```text
http://127.0.0.1:5000
```

---

## 🔑 Demo Accounts

The project includes pre-seeded demo accounts for quick testing:

| Role | Email | Password | Organization |
| :--- | :--- | :--- | :--- |
| **Donor** | `donor@grandhotel.com` | `password123` | Grand Palace Hotel |
| **Donor** | `events@royalbanquet.com` | `password123` | Royal Banquets |
| **NGO** | `ngo@foodcare.org` | `password123` | FoodCare Foundation |
| **NGO** | `volunteer@hopehouse.org` | `password123` | Hope Shelter |

*(Note: Clickable demo buttons are available directly on the login page for 1-click auto-fill).*

---

## 🗄️ Database Schema

### `users`
- `id` (INTEGER, Primary Key)
- `name` (TEXT)
- `email` (TEXT, Unique)
- `password_hash` (TEXT)
- `role` (TEXT: `'donor'` or `'ngo'`)
- `phone` (TEXT)
- `organization` (TEXT)

### `donations`
- `id` (INTEGER, Primary Key)
- `donor_id` (INTEGER, Foreign Key -> `users.id`)
- `food_name` (TEXT)
- `quantity` (TEXT)
- `category` (TEXT)
- `location` (TEXT)
- `latitude` (REAL)
- `longitude` (REAL)
- `expiry_time` (TEXT)
- `notes` (TEXT)
- `status` (TEXT: `'Available'`, `'Picked'`, or `'Delivered'`)
- `ngo_id` (INTEGER, Foreign Key -> `users.id`, Nullable)

---

## 🔌 API Endpoints

- `GET /api/donations` - Returns JSON array of all food donations with map coordinates for Leaflet marker generation.

---

## 📝 License

This project is open-source and free to use for community food drive initiatives and educational purposes.
