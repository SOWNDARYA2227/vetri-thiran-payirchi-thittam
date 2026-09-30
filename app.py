import os
import json
import re
import base64
import shutil
import urllib.parse
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union

from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, Request, status, Cookie
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv

from gemini_utils import (
    get_home_recommendations,
    get_party_recommendations,
    get_jewelry_recommendations,
    HomeBudgetInput,
    PartyBudgetInput,
    JewelryBudgetInput,
    usd_to_inr
)

# Load environment variables
load_dotenv()

# App Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "pocketsmart_super_secret_jwt_key_2025_secure_auth")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# FastAPI app initialization
app = FastAPI(title="PocketSmart: AI Budget Planner")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


# --- Data Models ---

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None


class UserInDB(User):
    hashed_password: str


class RegisterUser(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    password: str


class UserSession:
    def __init__(self, username: str, login_time: datetime, last_activity: datetime, token: str, user_data: dict = None):
        self.username = username
        self.login_time = login_time
        self.last_activity = last_activity
        self.token = token
        self.user_data = user_data or {}


class HistoryItem:
    def __init__(self, item_id: str, timestamp: str, recommendation_type: str, input_summary: dict, result_summary: dict, full_result: dict):
        self.id = item_id
        self.timestamp = timestamp
        self.recommendation_type = recommendation_type
        self.input_summary = input_summary
        self.input = input_summary
        self.result_summary = result_summary
        self.summary = result_summary
        self.full_result = full_result


# --- In-Memory Stores ---
users_db: Dict[str, UserInDB] = {
    "sai": UserInDB(
        username="sai",
        email="sai@example.com",
        full_name="Sai Kumar",
        hashed_password=pwd_context.hash("password123"),
        disabled=False
    ),
    "admin": UserInDB(
        username="admin",
        email="admin@pocketsmart.ai",
        full_name="PocketSmart Administrator",
        hashed_password=pwd_context.hash("admin123"),
        disabled=False
    )
}

active_sessions: Dict[str, UserSession] = {}
blacklisted_tokens: set = set()
user_recommendations: Dict[str, List[HistoryItem]] = {
    "sai": [
        HistoryItem(
            item_id="rec-demo-3",
            timestamp="May 22, 2025, 12:06 PM",
            recommendation_type="jewelry",
            input_summary={"total_budget": 5000, "occasion": "Birthday", "has_image": True},
            result_summary={"total_budget": 5000, "remaining_budget": 800, "items_count": 3},
            full_result={
                "total_budget": 5000,
                "remaining_budget": 800,
                "outfit_analysis": {"colors": ["Blue", "White"], "style": "Casual", "formality": "Informal"},
                "jewelry_recommendations": [
                    {"item_type": "Bracelet", "description": "Braided leather bracelet with metal accents.", "style": "Casual", "estimated_price": 500.0, "search_terms": "braided leather bracelet", "shopping_links": {"amazon": "https://www.amazon.in/s?k=braided+leather+bracelet", "flipkart": "https://www.flipkart.com/search?q=braided+leather+bracelet", "bluestone": "https://www.bluestone.com", "tanishq": "https://www.tanishq.co.in", "caratlane": "https://www.caratlane.com", "melorra": "https://www.melorra.com", "meesho": "https://www.meesho.com"}},
                    {"item_type": "Ring", "description": "Minimalist silver finish band.", "style": "Minimalist", "estimated_price": 700.0, "search_terms": "silver minimalist band ring", "shopping_links": {"amazon": "https://www.amazon.in/s?k=silver+band+ring", "flipkart": "https://www.flipkart.com/search?q=silver+band+ring", "bluestone": "https://www.bluestone.com", "tanishq": "https://www.tanishq.co.in", "caratlane": "https://www.caratlane.com", "melorra": "https://www.melorra.com", "meesho": "https://www.meesho.com"}},
                    {"item_type": "Watch", "description": "Classic simple watch with leather strap.", "style": "Classic", "estimated_price": 3000.0, "search_terms": "classic leather watch", "shopping_links": {"amazon": "https://www.amazon.in/s?k=classic+leather+watch", "flipkart": "https://www.flipkart.com/search?q=classic+leather+watch", "bluestone": "https://www.bluestone.com", "tanishq": "https://www.tanishq.co.in", "caratlane": "https://www.caratlane.com", "melorra": "https://www.melorra.com", "meesho": "https://www.meesho.com"}}
                ],
                "styling_tips": [
                    "Keep jewelry minimal to match the casual aesthetic.",
                    "Consider the watch as the centerpiece accent."
                ]
            }
        ),
        HistoryItem(
            item_id="rec-demo-2",
            timestamp="May 22, 2025, 12:05 PM",
            recommendation_type="party",
            input_summary={"total_budget": 5000, "party_type": "wedding", "guests": 3, "needs": ["Catering", "Entertainment"]},
            result_summary={"total_budget": 5000, "remaining_budget": 0, "categories": ["venue", "catering", "entertainment", "Contingency"]},
            full_result={
                "total_budget": 5000,
                "remaining_budget": 0,
                "budget_breakdown": [
                    {"category": "venue", "allocation": 0, "items": [{"name": "Home Living Venue", "description": "Utilizing home venue.", "estimated_price": 0, "quantity": 1, "shopping_links": {"google": "https://www.google.com", "booking": "https://www.booking.com", "makemytrip": "https://www.makemytrip.com", "oyorooms": "https://www.oyorooms.com", "nobroker": "https://www.nobroker.in"}}]},
                    {"category": "catering", "allocation": 2000, "items": [{"name": "Home-style celebration feast", "description": "Special meal catering for 3.", "estimated_price": 2000, "quantity": 1, "shopping_links": {"swiggy": "https://www.swiggy.com", "zomato": "https://www.zomato.com"}}]},
                    {"category": "entertainment", "allocation": 2000, "items": [{"name": "Streaming & Music & Gifts", "description": "Music playlist & party favors.", "estimated_price": 2000, "quantity": 1, "shopping_links": {"amazon": "https://www.amazon.in", "flipkart": "https://www.flipkart.com", "bookmyshow": "https://in.bookmyshow.com"}}]},
                    {"category": "contingency", "allocation": 1000, "items": [{"name": "Unexpected expenses buffer", "description": "Contingency fund.", "estimated_price": 1000, "quantity": 1, "shopping_links": {"amazon": "https://www.amazon.in", "flipkart": "https://www.flipkart.com", "google": "https://www.google.com"}}]}
                ],
                "venue_suggestions": [{"name": "Home Setting", "type": "Residential", "capacity": 5, "estimated_cost": 0}],
                "additional_suggestions": ["Order party platters in advance.", "Prepare a curated celebration music playlist."]
            }
        ),
        HistoryItem(
            item_id="rec-demo-1",
            timestamp="May 22, 2025, 12:02 PM",
            recommendation_type="home",
            input_summary={"total_budget": 5000, "rooms": ["Living Room", "Kitchen"], "num_lights": 5, "num_fans": 4, "num_furniture": 2},
            result_summary={"total_budget": 5000, "remaining_budget": 500, "categories": ["lighting", "ceiling_fans", "furniture"]},
            full_result={
                "total_budget": 5000,
                "remaining_budget": 500,
                "budget_breakdown": [
                    {"category": "lighting", "allocation": 1500, "items": [{"name": "LED Warm White Bulbs (Pack of 5)", "description": "Energy-efficient LED bulbs for ambient lighting.", "estimated_price": 100, "quantity": 5, "shopping_links": {"amazon": "https://www.amazon.in", "flipkart": "https://www.flipkart.com", "ikea": "https://www.ikea.com/in/en/", "myntra": "https://www.myntra.com", "ajio": "https://www.ajio.com"}}]},
                    {"category": "ceiling_fans", "allocation": 2000, "items": [{"name": "Havells Energy Saving Fans (4 units)", "description": "Functional ceiling fans.", "estimated_price": 500, "quantity": 4, "shopping_links": {"amazon": "https://www.amazon.in", "flipkart": "https://www.flipkart.com", "ikea": "https://www.ikea.com/in/en/", "myntra": "https://www.myntra.com", "ajio": "https://www.ajio.com"}}]},
                    {"category": "furniture", "allocation": 1000, "items": [{"name": "Accent Chairs & Wooden Side Table", "description": "Compact stackable chairs and wooden side table.", "estimated_price": 500, "quantity": 2, "shopping_links": {"amazon": "https://www.amazon.in", "flipkart": "https://www.flipkart.com", "ikea": "https://www.ikea.com/in/en/", "myntra": "https://www.myntra.com", "ajio": "https://www.ajio.com"}}]}
                ],
                "additional_suggestions": ["Opt for warm white lighting for cozy ambiance.", "Check modular furniture sales on Flipkart & IKEA."]
            }
        )
    ]
}


# --- Auth & Session Helper Functions ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(users: dict, username: str, password: str):
    user = users.get(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_token(request: Request, header_token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    """Retrieve token from Authorization header or from access_token cookie."""
    if header_token:
        return header_token
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:]
        return cookie_token
    return None


async def get_current_user(request: Request, token: Optional[str] = Depends(get_token)) -> Optional[UserInDB]:
    if not token:
        return None
    if token in blacklisted_tokens:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        token_data = TokenData(username=username)
    except JWTError:
        return None

    user = users_db.get(token_data.username)
    if user is None:
        return None

    # Update session last activity
    if user.username in active_sessions:
        active_sessions[user.username].last_activity = datetime.utcnow()

    return user


async def get_current_active_user(request: Request, current_user: Optional[UserInDB] = Depends(get_current_user)) -> UserInDB:
    if not current_user:
        # If accessing HTML page, redirect or raise 401
        if "text/html" in request.headers.get("accept", ""):
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": "/login"}
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def save_to_history(username: str, recommendation_type: str, input_data: dict, result: dict):
    """Save recommendation result to user history."""
    if username not in user_recommendations:
        user_recommendations[username] = []
    
    item_id = f"rec-{str(uuid.uuid4())[:8]}"
    timestamp = datetime.now().strftime("%B %d, %Y, %I:%M %p")
    
    # Create concise summaries for history list view
    input_summary = dict(input_data)
    result_summary = {
        "total_budget": result.get("total_budget", input_data.get("total_budget", 0)),
        "remaining_budget": result.get("remaining_budget", 0)
    }

    if recommendation_type == "home":
        categories = [cat.get("category", "") for cat in result.get("budget_breakdown", [])]
        result_summary["categories"] = categories
    elif recommendation_type == "party":
        categories = [cat.get("category", "") for cat in result.get("budget_breakdown", [])]
        result_summary["categories"] = categories
    elif recommendation_type == "jewelry":
        result_summary["items_count"] = len(result.get("jewelry_recommendations", []))

    history_item = HistoryItem(
        item_id=item_id,
        timestamp=timestamp,
        recommendation_type=recommendation_type,
        input_summary=input_summary,
        result_summary=result_summary,
        full_result=result
    )
    user_recommendations[username].insert(0, history_item)


def save_upload_file(upload_file: UploadFile) -> str:
    """Save uploaded image file to static/uploads/ and return local path."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_ext = os.path.splitext(upload_file.filename)[1] or ".jpg"
    filename = f"{timestamp}_{uuid.uuid4().hex[:6]}{file_ext}"
    file_path = os.path.join("static", "uploads", filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    
    return file_path


# --- HTML Page Routes ---

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request, current_user: Optional[UserInDB] = Depends(get_current_user)):
    """Landing Home Page"""
    return templates.TemplateResponse(request=request, name="index.html", context={"user": current_user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page"""
    try:
        token = await get_token(request)
        if token:
            user = await get_current_user(request, token)
            if user:
                return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except Exception:
        pass
    return templates.TemplateResponse(request=request, name="login.html", context={})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the registration page"""
    try:
        token = await get_token(request)
        if token:
            user = await get_current_user(request, token)
            if user:
                return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except Exception:
        pass
    return templates.TemplateResponse(request=request, name="register.html", context={})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """User dashboard page showing recent activity and quick access"""
    recent_history = user_recommendations.get(current_user.username, [])[:5]
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": current_user,
            "recent_history": recent_history
        }
    )


@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Home budget planner page"""
    return templates.TemplateResponse(request=request, name="home_planner.html", context={"user": current_user})


@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Party budget planner page"""
    return templates.TemplateResponse(request=request, name="party_planner.html", context={"user": current_user})


@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Jewelry budget planner page"""
    return templates.TemplateResponse(request=request, name="jewelry_planner.html", context={"user": current_user})


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """History page to view past recommendations"""
    history = user_recommendations.get(current_user.username, [])
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "user": current_user,
            "history": history
        }
    )


# --- Authentication Endpoints ---

@app.post("/register")
async def register(user_data: RegisterUser):
    """Handle new user registration"""
    if user_data.username in users_db:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user_data.password)
    new_user = UserInDB(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name or user_data.username,
        hashed_password=hashed_password,
        disabled=False
    )
    users_db[user_data.username] = new_user
    user_recommendations[user_data.username] = []
    
    return {"message": "Registration successful! You can now log in.", "username": user_data.username}


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint to get access token"""
    user = authenticate_user(users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    # Manage active sessions
    existing_user_data = {}
    if user.username in active_sessions:
        existing_user_data = active_sessions[user.username].user_data
        old_token = active_sessions[user.username].token
        blacklisted_tokens.add(old_token)

    active_sessions[user.username] = UserSession(
        username=user.username,
        login_time=datetime.utcnow(),
        last_activity=datetime.utcnow(),
        token=access_token,
        user_data=existing_user_data
    )

    response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return response


@app.post("/login")
async def login_form_handler(username: str = Form(...), password: str = Form(...)):
    """Form-based login handler for HTML forms"""
    user = authenticate_user(users_db, username, password)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid username or password")
    
    access_token = create_access_token(data={"sub": user.username})
    active_sessions[user.username] = UserSession(
        username=user.username,
        login_time=datetime.utcnow(),
        last_activity=datetime.utcnow(),
        token=access_token,
        user_data={}
    )
    response = JSONResponse(content={"status": "success", "redirect": "/dashboard", "access_token": access_token})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return response


@app.api_route("/logout", methods=["GET", "POST"])
async def logout(request: Request):
    """Logout user by blacklisting token and clearing session"""
    token = await get_token(request)
    if token:
        blacklisted_tokens.add(token)
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username and username in active_sessions:
                del active_sessions[username]
        except JWTError:
            pass

    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response


# --- Session Management Endpoints ---

@app.get("/session-info")
async def get_session_info(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Get current user's session information"""
    if current_user.username in active_sessions:
        session = active_sessions[current_user.username]
        return {
            "username": session.username,
            "login_time": session.login_time.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "session_duration_minutes": (datetime.utcnow() - session.login_time).total_seconds() // 60,
            "user_data": session.user_data
        }
    else:
        raise HTTPException(status_code=404, detail="No active session found")


@app.post("/session-data")
async def update_session_data(
    data: Dict[str, Any],
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Update user's session data"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data.update(data)
        active_sessions[current_user.username].last_activity = datetime.utcnow()
        return {"message": "Session data updated", "data": active_sessions[current_user.username].user_data}
    else:
        raise HTTPException(status_code=404, detail="No active session found")


# --- Planner Recommendation Endpoints ---

@app.post("/home-budget")
@app.post("/generate-home")
async def plan_home_budget(
    budget_input: HomeBudgetInput,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate home budget recommendations"""
    # Store in session data
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_home_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "requirements": {
                "lights": budget_input.num_lights,
                "fans": budget_input.num_fans,
                "furniture": budget_input.num_furniture,
                "dining_tables": budget_input.num_dining_tables
            }
        }

    # Get AI recommendations
    result = get_home_recommendations(budget_input)

    # Save to history
    save_to_history(
        username=current_user.username,
        recommendation_type="home",
        input_data=budget_input.dict(),
        result=result
    )

    return result


@app.post("/party-budget")
@app.post("/generate-party")
async def plan_party_budget(
    budget_input: PartyBudgetInput,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate party budget recommendations"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_party_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "party_type": budget_input.party_type,
            "guests": budget_input.num_guests
        }

    result = get_party_recommendations(budget_input)

    save_to_history(
        username=current_user.username,
        recommendation_type="party",
        input_data=budget_input.dict(),
        result=result
    )

    return result


@app.post("/jewelry-budget")
@app.post("/generate-jewelry")
async def plan_jewelry_budget(
    total_budget: float = Form(...),
    occasion: str = Form(...),
    preferences: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    request: Request = None,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate jewelry budget recommendations with optional outfit image"""
    budget_input = JewelryBudgetInput(
        total_budget=total_budget,
        occasion=occasion,
        preferences=preferences
    )

    image_path = None
    if image and image.filename:
        image_path = save_upload_file(image)

    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_jewelry_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "occasion": budget_input.occasion,
            "has_image": image is not None
        }

    result = get_jewelry_recommendations(budget_input, image_path)

    input_data = budget_input.dict()
    if image and image.filename:
        input_data["image"] = image.filename
        if image_path:
            # Store relative url for web preview
            input_data["image_url"] = "/" + image_path.replace("\\", "/")

    save_to_history(
        username=current_user.username,
        recommendation_type="jewelry",
        input_data=input_data,
        result=result
    )

    return result


# --- History Endpoints ---

@app.get("/recommendation-history")
async def get_recommendation_history(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Get the user's recommendation history list"""
    if current_user.username not in user_recommendations:
        return {"history": []}

    history = sorted(
        user_recommendations[current_user.username],
        key=lambda x: x.timestamp,
        reverse=True
    )

    history_data = []
    for item in history:
        history_data.append({
            "id": item.id,
            "timestamp": item.timestamp,
            "type": item.recommendation_type,
            "input": item.input_summary,
            "summary": item.result_summary
        })

    return {"history": history_data}


@app.get("/recommendation-details/{recommendation_id}")
async def get_recommendation_details(
    recommendation_id: str,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Get full details of a specific recommendation item"""
    if current_user.username not in user_recommendations:
        raise HTTPException(status_code=404, detail="No recommendations found")

    for item in user_recommendations[current_user.username]:
        if item.id == recommendation_id:
            return {
                "id": item.id,
                "timestamp": item.timestamp,
                "type": item.recommendation_type,
                "input": item.input_summary,
                "full_result": item.full_result
            }

    raise HTTPException(status_code=404, detail="Recommendation not found")


# --- Background Tasks & Lifespan ---

@app.on_event("startup")
async def setup_session_cleanup():
    """Background task to clean up expired sessions"""
    async def cleanup_expired_sessions():
        while True:
            current_time = datetime.utcnow()
            expired_sessions = [
                username for username, session in list(active_sessions.items())
                if (current_time - session.last_activity).total_seconds() > (ACCESS_TOKEN_EXPIRE_MINUTES * 60)
            ]

            for username in expired_sessions:
                if username in active_sessions:
                    print(f"Removing expired session for {username}")
                    del active_sessions[username]

            await asyncio.sleep(300)

    asyncio.create_task(cleanup_expired_sessions())


# --- Main Entry Point ---

if __name__ == "__main__":
    import uvicorn
    print("Starting PocketSmart: AI Budget Planner on http://localhost:8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
