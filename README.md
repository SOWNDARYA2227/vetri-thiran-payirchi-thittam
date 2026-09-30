# PocketSmart AI: Your Smart Budget & Recommendation Assistant

PocketSmart AI is a GenAI-powered, cross-platform recommendation system designed to provide personalized, budget-based suggestions for products and services across three primary lifestyle scenarios:
1. **Home Interior Planning with Smart Budget Allocation**
2. **AI-Based Party & Event Budget Planning**
3. **Jewelry Recommendations for Occasions with Multimodal Outfit Analysis**

Powered by **Google Gemini 1.5 Flash Pro** and built on **FastAPI**, PocketSmart AI transforms budgeting into an intelligent and user-friendly experience with direct shopping/booking links from popular Indian platforms including Amazon, Flipkart, IKEA, Swiggy, Zomato, BookMyShow, MakeMyTrip, OYO, Bluestone, Tanishq, CaratLane, and Meesho.

---

## 🌟 Key Features

- **Home Interior Budget Planner** (`/home-planner`):
  - User defines total budget in INR, number of lights, ceiling fans, furniture pieces, dining tables, and room choices (Living Room, Kitchen, Bedroom).
  - Gemini AI analyzes constraints and allocates budget across categories with product recommendations and shopping links (Amazon India, Flipkart, IKEA India, Myntra, Ajio).
  - Displays detailed allocation calculation table and energy-saving design tips.

- **Party & Event Budget Planner** (`/party-planner`):
  - User enters total budget, guest count, party type (Wedding, Birthday, Anniversary, Corporate, House Party), venue type, and specific needs (Catering, Decoration, Entertainment).
  - AI allocates budget proportionally across food/catering, decor, music/entertainment, venue, and emergency contingency buffers.
  - Sourcing links for Swiggy, Zomato, BigBasket, BookMyShow, OYO Rooms, MakeMyTrip, NoBroker, etc.
  - Generates downloadable/printable budget plan.

- **Jewelry Budget Planner** (`/jewelry-planner`):
  - User enters budget, occasion, style preferences, and optionally uploads an outfit photo.
  - Multimodal Gemini AI performs visual color palette and formality analysis of the outfit.
  - Generates style-coordinated jewelry pieces (necklaces, earrings, jhumkas, bracelets, rings) with shopping links to Tanishq, BlueStone, CaratLane, Melorra, Amazon, and Meesho.

- **Recommendation History & Activity Dashboard** (`/history`, `/dashboard`):
  - Tracks and stores all budget plans and recommendation queries.
  - Interactive modal dialog to view complete cost breakdowns and direct links anytime.

- **Authentication & Session Management**:
  - Secure JWT authentication with HTTP-only cookies and bcrypt password hashing.
  - Session activity tracking and automated session cleanup.

---

## 📁 Project Structure

```
pocketsmart-AI/
├── app.py                     # Main FastAPI application and routing layer
├── gemini_utils.py            # AI integration, prompt orchestration, shopping link generation
├── requirements.txt           # Python package dependencies
├── .env                       # Environment variables configuration
├── static/
│   ├── uploads/               # Uploaded outfit images directory
│   └── styles.css             # Responsive CSS design and animations
└── templates/
    ├── base.html              # Base Jinja2 layout template
    ├── index.html             # Landing homepage with testimonials
    ├── login.html             # Login authentication page
    ├── register.html          # User registration page
    ├── dashboard.html         # User dashboard & recent activity
    ├── home_planner.html      # Home interior planner interface
    ├── party_planner.html     # Party budget planner interface
    ├── jewelry_planner.html   # Jewelry planner with outfit upload
    └── history.html           # Recommendation history page
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+ installed
- Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/))

### 2. Configure Environment Variables
Edit `.env` and configure your API key:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
SECRET_KEY=pocketsmart_super_secret_jwt_key_2025_secure_auth
ACCESS_TOKEN_EXPIRE_MINUTES=60
```
*(Note: If no API key is set, PocketSmart AI automatically switches to its smart offline recommendation engine for seamless local testing).*

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```bash
python app.py
```
Or with Uvicorn live-reload:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to:
```
http://localhost:8000
```

### 5. Demo Credentials
- **Username**: `sai`
- **Password**: `password123`
- *(Or register any new account via `/register`)*

---

## 🛠️ API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Landing page |
| `GET` | `/login`, `/register` | Auth pages |
| `POST` | `/login`, `/token`, `/register` | Authentication handlers |
| `GET` | `/dashboard` | User dashboard |
| `GET` | `/home-planner` | Home planner UI |
| `POST` | `/home-budget`, `/generate-home` | Home budget recommendation API |
| `GET` | `/party-planner` | Party planner UI |
| `POST` | `/party-budget`, `/generate-party` | Party budget recommendation API |
| `GET` | `/jewelry-planner` | Jewelry planner UI |
| `POST` | `/jewelry-budget`, `/generate-jewelry`| Multimodal jewelry recommendation API |
| `GET` | `/history` | History page |
| `GET` | `/recommendation-history` | List user's past recommendations |
| `GET` | `/recommendation-details/{id}` | Get full details for recommendation ID |
| `GET` | `/session-info`, `/session-data` | User session metadata |
