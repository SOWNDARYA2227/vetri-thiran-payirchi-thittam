import os
import json
import re
import urllib.parse
from typing import Optional, Dict, Any, List
from PIL import Image
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Setup Google Gemini AI
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
model = None

if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        # Choose flash model for fast and high-quality responses
        model = genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        print(f"Warning: Could not initialize Gemini API: {e}")
        model = None


# --- Pydantic Input Models ---

class HomeBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0, description="Total budget in INR or USD")
    num_lights: int = Field(0, ge=0)
    num_fans: int = Field(0, ge=0)
    num_furniture: int = Field(0, ge=0)
    num_dining_tables: int = Field(0, ge=0)
    has_living_room: bool = False
    has_kitchen: bool = False
    has_bedroom: bool = False
    additional_requirements: Optional[str] = None


class PartyBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0, description="Total budget in INR")
    num_guests: int = Field(..., gt=0)
    party_type: str = "Birthday"
    venue_type: Optional[str] = "Home"
    needs_catering: bool = True
    needs_decoration: bool = True
    needs_entertainment: bool = True
    additional_requirements: Optional[str] = None


class JewelryBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0, description="Total budget in INR")
    occasion: str = "Wedding"
    preferences: Optional[str] = None


# --- Helper Functions ---

def extract_json_from_response(text: str) -> dict:
    """Extract and parse JSON object from Gemini response text."""
    if not text:
        return {}
    
    # Try finding markdown json codeblock
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        cleaned = match.group(1).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass

    # Try finding raw JSON between curly braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = text[start : end + 1]
        try:
            return json.loads(cleaned)
        except Exception:
            pass

    # Direct parse attempt
    try:
        return json.loads(text.strip())
    except Exception:
        return {}


def usd_to_inr(amount_usd: float, exchange_rate: float = 83.0) -> float:
    """Convert USD amount to INR using the specified exchange rate."""
    return amount_usd * exchange_rate


# --- Home Recommendations Logic ---

def get_home_recommendations(budget_input: HomeBudgetInput) -> dict:
    """Generate home interior recommendations within budget in INR for Indian market."""
    total_budget = float(budget_input.total_budget)
    
    rooms = []
    if budget_input.has_living_room:
        rooms.append("Living Room")
    if budget_input.has_kitchen:
        rooms.append("Kitchen")
    if budget_input.has_bedroom:
        rooms.append("Bedroom")
    rooms_str = ", ".join(rooms) if rooms else "General Home"

    prompt = f"""
I need interior design product recommendations for a home in India with a total budget of ₹{total_budget:.2f}.
Requirements:
- {budget_input.num_lights} lights/lighting fixtures
- {budget_input.num_fans} ceiling fans
- {budget_input.num_furniture} furniture pieces
- {budget_input.num_dining_tables} dining tables

Additional rooms to consider:
{'- Living room' if budget_input.has_living_room else ''}
{'- Kitchen' if budget_input.has_kitchen else ''}
{'- Bedroom' if budget_input.has_bedroom else ''}

Additional requirements: {budget_input.additional_requirements or "None"}

Please provide a detailed budget breakdown with product recommendations **available in India**.
Use **Indian brands and pricing** in INR. Include **search terms** suitable for Indian shopping platforms.

Format your response strictly as JSON with the following structure:
{{
  "total_budget": {total_budget:.2f},
  "budget_breakdown": [
    {{
      "category": "Lighting",
      "allocation": 0.0,
      "items": [
        {{
          "name": "LED Warm Ceiling Spotlight",
          "description": "Energy-efficient LED spotlights for modern ambient lighting.",
          "estimated_price": 500.0,
          "quantity": {max(budget_input.num_lights, 1)},
          "search_terms": "LED warm spotlight ceiling lights"
        }}
      ]
    }}
  ],
  "calculation_table": [
    {{
      "category": "Lighting",
      "items_count": 1,
      "total_cost": 500.0,
      "percentage_of_budget": 10.0
    }}
  ],
  "remaining_budget": 0.0,
  "additional_suggestions": [
    "Consider energy efficient 5-star rated BLDC fans for lower electricity costs.",
    "Look for modular furniture with built-in storage to maximize living room space."
  ]
}}

Ensure total costs stay within budget. Include realistic search terms for shopping websites like Flipkart, Amazon India, IKEA India, Myntra, and Ajio.
"""

    result = None
    if model:
        try:
            response = model.generate_content(prompt)
            result = extract_json_from_response(response.text)
        except Exception as e:
            print(f"Gemini API error in home planner: {e}")

    # Fallback if AI call failed or returned empty
    if not result or not result.get("budget_breakdown"):
        result = _generate_fallback_home_recommendations(budget_input)

    # Add shopping links for each item
    for category in result.get("budget_breakdown", []):
        for item in category.get("items", []):
            search_terms = item.get("search_terms") or item.get("name", "")
            if search_terms:
                encoded = urllib.parse.quote_plus(search_terms)
                item["shopping_links"] = {
                    "amazon": f"https://www.amazon.in/s?k={encoded}",
                    "flipkart": f"https://www.flipkart.com/search?q={encoded}",
                    "ikea": f"https://www.ikea.com/in/en/search/?q={encoded}",
                    "myntra": f"https://www.myntra.com/search?q={encoded}",
                    "ajio": f"https://www.ajio.com/search/?text={encoded}"
                }

    # Ensure calculation table and totals are accurate
    calc_table = []
    total_spent = 0.0
    for category in result.get("budget_breakdown", []):
        cat_name = category.get("category", "General")
        items = category.get("items", [])
        cat_items_count = sum(item.get("quantity", 1) for item in items)
        cat_cost = sum(item.get("estimated_price", 0) * item.get("quantity", 1) for item in items)
        total_spent += cat_cost
        category["allocation"] = round(cat_cost, 2)
        pct = round((cat_cost / total_budget * 100), 1) if total_budget > 0 else 0
        calc_table.append({
            "category": cat_name,
            "items_count": cat_items_count,
            "total_cost": round(cat_cost, 2),
            "percentage_of_budget": pct
        })

    result["calculation_table"] = calc_table
    result["total_budget"] = total_budget
    result["remaining_budget"] = round(max(0.0, total_budget - total_spent), 2)
    
    return result


def _generate_fallback_home_recommendations(budget_input: HomeBudgetInput) -> dict:
    """Smart algorithmic fallback for Home Planner."""
    total = float(budget_input.total_budget)
    
    categories = []
    
    # Lighting
    lights_qty = budget_input.num_lights if budget_input.num_lights > 0 else 3
    light_price = min(round((total * 0.15) / lights_qty, 2), 600.0)
    categories.append({
        "category": "Lighting",
        "allocation": round(light_price * lights_qty, 2),
        "items": [
            {
                "name": "Philips / Wipro Smart LED Batten & Bulb Pack",
                "description": "Energy-efficient LED bulbs and warm track ambient spotlights.",
                "estimated_price": light_price,
                "quantity": lights_qty,
                "search_terms": "Philips Warm White Smart LED Batten Lights"
            }
        ]
    })
    
    # Ceiling Fans
    fans_qty = budget_input.num_fans if budget_input.num_fans > 0 else 2
    fan_price = min(round((total * 0.25) / fans_qty, 2), 2400.0)
    categories.append({
        "category": "Ceiling Fans",
        "allocation": round(fan_price * fans_qty, 2),
        "items": [
            {
                "name": "Atomberg / Havells BLDC Energy Saver Fan",
                "description": "Silent, remote-controlled 5-star energy efficient ceiling fan.",
                "estimated_price": fan_price,
                "quantity": fans_qty,
                "search_terms": "Havells BLDC 1200mm ceiling fan"
            }
        ]
    })

    # Furniture
    furn_qty = budget_input.num_furniture if budget_input.num_furniture > 0 else 2
    furn_price = min(round((total * 0.35) / furn_qty, 2), 4500.0)
    categories.append({
        "category": "Furniture",
        "allocation": round(furn_price * furn_qty, 2),
        "items": [
            {
                "name": "Ergonomic Lounge Accent Chairs & Coffee Table",
                "description": "Modern minimalist wooden finish living room accent chair and side table.",
                "estimated_price": furn_price,
                "quantity": furn_qty,
                "search_terms": "Modern wooden accent chair coffee table"
            }
        ]
    })

    # Dining Tables
    if budget_input.num_dining_tables > 0:
        table_qty = budget_input.num_dining_tables
        table_price = min(round((total * 0.15) / table_qty, 2), 6000.0)
        categories.append({
            "category": "Dining Furniture",
            "allocation": round(table_price * table_qty, 2),
            "items": [
                {
                    "name": "4-Seater Compact Engineered Wood Dining Set",
                    "description": "Space-saving dining table with matching cushioned chairs.",
                    "estimated_price": table_price,
                    "quantity": table_qty,
                    "search_terms": "4 seater compact wooden dining table set"
                }
            ]
        })

    return {
        "total_budget": total,
        "budget_breakdown": categories,
        "additional_suggestions": [
            "Opt for warm white (3000K) lighting for cozy living rooms and daylight white (4000K) in kitchens.",
            "Consider purchasing modular or foldable furniture from IKEA India for compact room layouts.",
            "Check festive discount deals on Amazon and Flipkart for bundled electronics and home decor."
        ]
    }


# --- Party Recommendations Logic ---

def get_party_recommendations(budget_input: PartyBudgetInput) -> dict:
    """Generate party planning recommendations within budget in INR for Indian market."""
    total_budget = float(budget_input.total_budget)
    
    prompt = f"""
I need party planning recommendations for India with a total budget of ₹{total_budget:.2f}.

Party details:
- Type: {budget_input.party_type}
- Number of guests: {budget_input.num_guests}
- Venue type: {budget_input.venue_type or "Not specified"}
- Catering needed: {"Yes" if budget_input.needs_catering else "No"}
- Decoration needed: {"Yes" if budget_input.needs_decoration else "No"}
- Entertainment needed: {"Yes" if budget_input.needs_entertainment else "No"}

Additional requirements: {budget_input.additional_requirements or "None"}

Please provide a detailed budget breakdown with specific recommendations available in India using INR prices.
Use Indian brands, services, and typical cost expectations.

Format your response strictly as JSON with the following structure:
{{
  "total_budget": {total_budget:.2f},
  "budget_breakdown": [
    {{
      "category": "venue",
      "allocation": 0.0,
      "items": [
        {{
          "name": "Home Living / Terrace Setup",
          "description": "Utilizing private home or rented clubhouse venue.",
          "estimated_price": 0.0,
          "quantity": 1,
          "search_terms": "party venue hall rental"
        }}
      ]
    }},
    {{
      "category": "catering",
      "allocation": 0.0,
      "items": [
        {{
          "name": "Party Buffet & Finger Food Platter",
          "description": "Appetizers, mains and desserts catering per head.",
          "estimated_price": 2000.0,
          "quantity": 1,
          "search_terms": "party catering food bulk order"
        }}
      ]
    }},
    {{
      "category": "decoration",
      "allocation": 0.0,
      "items": [
        {{
          "name": "Theme Balloon Arch & Fairy Lights Kit",
          "description": "Vibrant party backdrop, confetti balloons, and photo-booth props.",
          "estimated_price": 800.0,
          "quantity": 1,
          "search_terms": "birthday party decoration kit balloons"
        }}
      ]
    }},
    {{
      "category": "entertainment",
      "allocation": 0.0,
      "items": [
        {{
          "name": "Music & Party Games Pack",
          "description": "Party board games, portable karaoke microphone or playlist setup.",
          "estimated_price": 500.0,
          "quantity": 1,
          "search_terms": "wireless karaoke mic bluetooth party games"
        }}
      ]
    }}
  ],
  "venue_suggestions": [
    {{
      "name": "Local Community Hall / OYO Townhouse Party Space",
      "type": "Hall / Banquet",
      "capacity": {budget_input.num_guests + 10},
      "estimated_cost": 2500.0,
      "search_terms": "party hall venue booking"
    }}
  ],
  "remaining_budget": 0.0,
  "additional_suggestions": [
    "Order finger foods and party appetizers via Swiggy or Zomato for prompt bulk delivery.",
    "Curate a collaborative Spotify / YouTube Music playlist to save on dedicated DJ costs.",
    "Use reusable fairy lights and photo props for memorable Instagram snapshots."
  ]
}}

Ensure all costs are in INR and total does not exceed the given budget.
Provide search terms suitable for Indian websites such as BookMyShow, Swiggy, Flipkart, etc.
"""

    result = None
    if model:
        try:
            response = model.generate_content(prompt)
            result = extract_json_from_response(response.text)
        except Exception as e:
            print(f"Gemini API error in party planner: {e}")

    if not result or not result.get("budget_breakdown"):
        result = _generate_fallback_party_recommendations(budget_input)

    # Define platform mappings per category
    category_platforms = {
        "venue": ["google", "booking", "makemytrip", "oyorooms", "nobroker"],
        "catering": ["swiggy", "zomato", "bigbasket"],
        "food": ["swiggy", "zomato", "bigbasket", "amazon", "flipkart"],
        "drinks": ["swiggy", "zomato", "bigbasket", "amazon", "flipkart"],
        "decoration": ["amazon", "flipkart", "meesho", "myntra"],
        "entertainment": ["bookmyshow", "amazon", "flipkart"],
        "gifts": ["amazon", "flipkart", "myntra", "meesho"],
        "photography": ["google", "amazon", "flipkart"],
        "music": ["amazon", "flipkart", "bookmyshow"],
        "games": ["amazon", "flipkart"],
        "accessories": ["amazon", "flipkart", "myntra", "meesho"],
        "transportation": ["makemytrip", "google"],
        "return_gifts": ["amazon", "flipkart", "myntra", "meesho"],
        "contingency": ["amazon", "flipkart", "google"]
    }
    default_platforms = ["amazon", "flipkart", "google"]

    # Calculate INR breakdown table & attach links
    result["calculation_table_inr"] = []
    categories_calc = {}

    for category in result.get("budget_breakdown", []):
        cat_name = category.get("category", "Misc").strip().lower()
        cat_title = category.get("category", "Misc")
        relevant_platforms = category_platforms.get(cat_name, default_platforms)

        if cat_title not in categories_calc:
            categories_calc[cat_title] = {
                "category": cat_title,
                "items_count": 0,
                "total_cost": 0.0,
                "percentage_of_budget": 0.0
            }

        for item in category.get("items", []):
            qty = item.get("quantity", 1)
            price = float(item.get("estimated_price", 0))
            categories_calc[cat_title]["items_count"] += qty
            categories_calc[cat_title]["total_cost"] += (price * qty)

            search_terms = item.get("search_terms") or item.get("name", "")
            if search_terms:
                encoded = urllib.parse.quote_plus(search_terms)
                item["shopping_links"] = {}
                if "amazon" in relevant_platforms:
                    item["shopping_links"]["amazon"] = f"https://www.amazon.in/s?k={encoded}"
                if "flipkart" in relevant_platforms:
                    item["shopping_links"]["flipkart"] = f"https://www.flipkart.com/search?q={encoded}"
                if "bigbasket" in relevant_platforms:
                    item["shopping_links"]["bigbasket"] = f"https://www.bigbasket.com/ps/?q={encoded}"
                if "swiggy" in relevant_platforms:
                    item["shopping_links"]["swiggy"] = f"https://www.swiggy.com/search?query={encoded}"
                if "zomato" in relevant_platforms:
                    item["shopping_links"]["zomato"] = f"https://www.zomato.com/search?q={encoded}"
                if "bookmyshow" in relevant_platforms:
                    item["shopping_links"]["bookmyshow"] = f"https://in.bookmyshow.com/search?q={encoded}"
                if "myntra" in relevant_platforms:
                    item["shopping_links"]["myntra"] = f"https://www.myntra.com/search?q={encoded}"
                if "meesho" in relevant_platforms:
                    item["shopping_links"]["meesho"] = f"https://www.meesho.com/search?q={encoded}"
                if "google" in relevant_platforms:
                    item["shopping_links"]["google"] = f"https://www.google.com/search?q={encoded}"
                if "booking" in relevant_platforms:
                    item["shopping_links"]["booking"] = f"https://www.booking.com/search.html?ss={encoded}"
                if "makemytrip" in relevant_platforms:
                    item["shopping_links"]["makemytrip"] = f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={encoded}"
                if "oyorooms" in relevant_platforms:
                    item["shopping_links"]["oyorooms"] = f"https://www.oyorooms.com/search/?location={encoded}"
                if "nobroker" in relevant_platforms:
                    item["shopping_links"]["nobroker"] = f"https://www.nobroker.in/property/search?searchTerm={encoded}"

    # Build calculation table
    total_spent = 0.0
    for cat_data in categories_calc.values():
        cat_cost = cat_data["total_cost"]
        total_spent += cat_cost
        if total_budget > 0:
            cat_data["percentage_of_budget"] = round((cat_cost / total_budget) * 100, 1)
        cat_data["total_cost"] = round(cat_cost, 2)
        result["calculation_table_inr"].append(cat_data)

    # Process venue suggestions search links
    venue_platforms = ["google", "booking", "makemytrip", "oyorooms", "nobroker"]
    for venue in result.get("venue_suggestions", []):
        search_terms = venue.get("search_terms") or venue.get("name", "")
        if search_terms:
            encoded = urllib.parse.quote_plus(search_terms)
            venue["search_links"] = {
                "google": f"https://www.google.com/search?q={encoded}",
                "booking": f"https://www.booking.com/search.html?ss={encoded}",
                "makemytrip": f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={encoded}",
                "oyorooms": f"https://www.oyorooms.com/search/?location={encoded}",
                "nobroker": f"https://www.nobroker.in/property/search?searchTerm={encoded}"
            }

    result["total_budget"] = total_budget
    result["remaining_budget"] = round(max(0.0, total_budget - total_spent), 2)
    return result


def _generate_fallback_party_recommendations(budget_input: PartyBudgetInput) -> dict:
    """Smart algorithmic fallback for Party Planner."""
    total = float(budget_input.total_budget)
    guests = max(budget_input.num_guests, 1)
    
    catering_cost = round(total * 0.40, 2) if budget_input.needs_catering else 0.0
    decor_cost = round(total * 0.20, 2) if budget_input.needs_decoration else 0.0
    ent_cost = round(total * 0.20, 2) if budget_input.needs_entertainment else 0.0
    venue_cost = round(total * 0.10, 2)
    contingency = round(max(0.0, total - (catering_cost + decor_cost + ent_cost + venue_cost)), 2)

    categories = [
        {
            "category": "venue",
            "allocation": venue_cost,
            "items": [
                {
                    "name": f"{budget_input.venue_type or 'Home / Garden Space'}",
                    "description": f"Private ambient setting tailored for {guests} guests.",
                    "estimated_price": venue_cost,
                    "quantity": 1,
                    "search_terms": f"party hall venue booking for {guests} guests"
                }
            ]
        },
        {
            "category": "catering",
            "allocation": catering_cost,
            "items": [
                {
                    "name": f"{budget_input.party_type} Gourmet Feast & Snack Box",
                    "description": f"Curated catering combo: appetizers, mocktails, main course, and dessert for {guests} people.",
                    "estimated_price": catering_cost,
                    "quantity": 1,
                    "search_terms": "bulk party catering food box delivery"
                }
            ]
        },
        {
            "category": "decoration",
            "allocation": decor_cost,
            "items": [
                {
                    "name": f"{budget_input.party_type} Grand Theme Decor Kit",
                    "description": "Foil balloon banner, pastel balloon garland, fairy LED curtain lights, and photo props.",
                    "estimated_price": decor_cost,
                    "quantity": 1,
                    "search_terms": "party theme decoration set fairy lights balloons"
                }
            ]
        },
        {
            "category": "entertainment",
            "allocation": ent_cost,
            "items": [
                {
                    "name": "Party Speaker, Karaoke Mic & Fun Board Games",
                    "description": "Portable Bluetooth party speaker with karaoke microphone and engaging party games.",
                    "estimated_price": ent_cost,
                    "quantity": 1,
                    "search_terms": "bluetooth party speaker karaoke mic"
                }
            ]
        }
    ]

    if contingency > 0:
        categories.append({
            "category": "contingency",
            "allocation": contingency,
            "items": [
                {
                    "name": "Buffer & Miscellaneous Supplies",
                    "description": "Emergency budget buffer for disposables, ice, extra beverages, or tip.",
                    "estimated_price": contingency,
                    "quantity": 1,
                    "search_terms": "biodegradable party tableware disposables"
                }
            ]
        })

    return {
        "total_budget": total,
        "budget_breakdown": categories,
        "venue_suggestions": [
            {
                "name": f"Local Cozy Banquet / {budget_input.venue_type or 'Townhouse Hall'}",
                "type": budget_input.venue_type or "Banquet Hall",
                "capacity": guests + 5,
                "estimated_cost": venue_cost,
                "search_terms": f"event party hall venue booking for {guests} guests"
            }
        ],
        "additional_suggestions": [
            "Pre-order catering via Swiggy or Zomato party orders to avail group discount deals.",
            "Set up a dedicated selfie-corner using fairy lights and balloon garland for memorable photos.",
            "Keep 10-15% of your budget reserved for last-minute snacks and beverage top-ups."
        ]
    }


# --- Jewelry Recommendations Logic ---

def get_jewelry_recommendations(budget_input: JewelryBudgetInput, image_path: Optional[str] = None) -> dict:
    """Generate jewelry recommendations based on uploaded outfit and budget in INR (India-specific)."""
    total_budget = float(budget_input.total_budget)
    base_prompt = f"""
I need jewelry recommendations for India with a total budget of ₹{total_budget:.2f}.

Occasion: {budget_input.occasion}
Preferences: {budget_input.preferences or "Not specified"}
Provide only India-relevant styles, availability, and price ranges in INR.
"""

    result = None
    if image_path and os.path.exists(image_path):
        prompt = base_prompt + """
An image of the outfit is uploaded. Suggest jewelry that complements it, considering color, design, and occasion appropriateness.

Format the output strictly as JSON with this structure:
{
  "outfit_analysis": {
    "colors": ["navy blue", "gold accents"],
    "style": "Ethnic Festive / Indo-Western",
    "formality": "Formal / Festive"
  },
  "total_budget": 5000.0,
  "jewelry_recommendations": [
    {
      "item_type": "Necklace / Choker",
      "description": "Kundan embellished choker set with matching drop pearls.",
      "style": "Traditional Kundan",
      "estimated_price": 2200.0,
      "search_terms": "kundan choker necklace set gold plated"
    },
    {
      "item_type": "Earrings / Jhumkas",
      "description": "Antique gold jhumkas with emerald green beads.",
      "style": "Ethnic Antique",
      "estimated_price": 1200.0,
      "search_terms": "antique gold plated jhumka earrings"
    },
    {
      "item_type": "Bangles / Bracelet",
      "description": "Gold plated kadas with intricate filigree work.",
      "style": "Contemporary Classic",
      "estimated_price": 900.0,
      "search_terms": "gold plated brass kadas bangles"
    }
  ],
  "remaining_budget": 700.0,
  "styling_tips": [
    "Pair the deep outfit color with gold or kundan jewelry for royal contrast.",
    "If the neckline is heavy, opt for statement earrings and skip a heavy neckpiece."
  ]
}

Make sure prices are in INR and stay within budget. Include Indian-friendly search terms for shopping.
"""
        if model:
            try:
                img = Image.open(image_path)
                response = model.generate_content([prompt, img])
                result = extract_json_from_response(response.text)
            except Exception as e:
                print(f"Gemini multimodal API error: {e}")

    else:
        prompt = base_prompt + f"""
Format the output strictly as JSON with this structure:
{{
  "outfit_analysis": {{
    "colors": ["Classic / Versatile"],
    "style": "{budget_input.occasion} Ready",
    "formality": "Semi-formal to Formal"
  }},
  "total_budget": {total_budget:.2f},
  "jewelry_recommendations": [
    {{
      "item_type": "Necklace",
      "description": "Delicate pendant chain or statement necklace suited for {budget_input.occasion}.",
      "style": "Contemporary Elegant",
      "estimated_price": {total_budget * 0.45:.2f},
      "search_terms": "sterling silver gold plated pendant necklace"
    }},
    {{
      "item_type": "Earrings",
      "description": "Matching drop or stud earrings.",
      "style": "Minimalist Classic",
      "estimated_price": {total_budget * 0.30:.2f},
      "search_terms": "fashion stud earrings cubic zirconia"
    }},
    {{
      "item_type": "Bracelet / Watch",
      "description": "Sleek metallic link bracelet or fashion wrist accessory.",
      "style": "Chic Modern",
      "estimated_price": {total_budget * 0.15:.2f},
      "search_terms": "adjustable charm bracelet rose gold"
    }}
  ],
  "remaining_budget": {total_budget * 0.10:.2f},
  "styling_tips": [
    "Balance statement pieces with subtle complements for an effortless look.",
    "Match metal tones (gold, silver, or rose gold) across your accessories."
  ]
}}

Keep prices in INR and relevant to Indian brands.
"""
        if model:
            try:
                response = model.generate_content(prompt)
                result = extract_json_from_response(response.text)
            except Exception as e:
                print(f"Gemini API error in jewelry planner: {e}")

    if not result or not result.get("jewelry_recommendations"):
        result = _generate_fallback_jewelry_recommendations(budget_input, image_path)

    # Add shopping links for each item (India-specific)
    for item in result.get("jewelry_recommendations", []):
        search_terms = item.get("search_terms") or item.get("item_type", "")
        if search_terms:
            encoded = urllib.parse.quote_plus(search_terms)
            item["shopping_links"] = {
                "amazon": f"https://www.amazon.in/s?k={encoded}",
                "flipkart": f"https://www.flipkart.com/search?q={encoded}",
                "bluestone": f"https://www.bluestone.com/search.html?query={encoded}",
                "tanishq": f"https://www.tanishq.co.in/search?q={encoded}",
                "caratlane": f"https://www.caratlane.com/search?q={encoded}",
                "melorra": f"https://www.melorra.com/search?q={encoded}",
                "meesho": f"https://www.meesho.com/search?q={encoded}"
            }

    # Recalculate remaining budget
    total_spent = sum(float(item.get("estimated_price", 0)) for item in result.get("jewelry_recommendations", []))
    result["total_budget"] = total_budget
    result["remaining_budget"] = round(max(0.0, total_budget - total_spent), 2)

    return result


def _generate_fallback_jewelry_recommendations(budget_input: JewelryBudgetInput, image_path: Optional[str] = None) -> dict:
    """Smart fallback for Jewelry Planner."""
    total = float(budget_input.total_budget)
    
    # Check if image was provided to give intelligent mock image analysis
    colors = ["Navy Blue", "Golden Shimmer"] if image_path else ["Festive Classic", "Rose Gold"]
    style = "Contemporary Indo-Western" if image_path else f"Modern {budget_input.occasion}"
    formality = "Festive / Elegant"

    p1 = round(total * 0.45, 2)
    p2 = round(total * 0.30, 2)
    p3 = round(total * 0.15, 2)

    return {
        "outfit_analysis": {
            "colors": colors,
            "style": style,
            "formality": formality
        },
        "total_budget": total,
        "jewelry_recommendations": [
            {
                "item_type": "Neckpiece / Pendant",
                "description": f"Chic statement jewelry piece handcrafted for {budget_input.occasion} occasions.",
                "style": "Kundan / Contemporary Rose Gold",
                "estimated_price": p1,
                "search_terms": f"designer {budget_input.occasion} necklace set"
            },
            {
                "item_type": "Earrings / Jhumkas",
                "description": "Sparkling crystal drop earrings designed to highlight facial contours.",
                "style": "Minimalist Classic",
                "estimated_price": p2,
                "search_terms": f"ethnic fashion jhumka earrings for {budget_input.occasion}"
            },
            {
                "item_type": "Bracelet / Bangle",
                "description": "Polished metallic cuff bracelet with delicate crystal stone accents.",
                "style": "Modern Chic",
                "estimated_price": p3,
                "search_terms": "adjustable metallic cuff bracelet with crystals"
            }
        ],
        "remaining_budget": round(max(0.0, total - (p1 + p2 + p3)), 2),
        "styling_tips": [
            f"Keep jewelry minimal and balanced to match the {budget_input.occasion} theme.",
            "Consider statement earrings as the focal point if wearing high neckline clothing.",
            "Ensure metal tones across rings, earrings, and bracelets remain cohesive."
        ]
    }
