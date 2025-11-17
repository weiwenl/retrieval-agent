# # Singapore Transport Agent
# Agentic system for discovering transport modes and carbon scoring for getting from accommodation to attractions and between attractions in Singapore.

# Install requirements if needed
# !pip install -r requirements.txt

# Imports
import os
import sys
import json
import logging
import math
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname('.'), 'src'))

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

# Configure logging
handlers = [logging.StreamHandler()]

# Add file handler only when running locally (not in Lambda)
if not os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
    handlers.append(logging.FileHandler('agent_reasoning.log', mode='a'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Check API keys
print("API Keys Status:")
print(f"GOOGLE_MAPS_API_KEY: {'Set' if os.getenv('GOOGLE_MAPS_API_KEY') else 'Missing'}")
print(f"OPENAI_API_KEY: {'Set' if os.getenv('OPENAI_API_KEY') else 'Missing'}")
print(f"ANTHROPIC_API_KEY: {'Set' if os.getenv('ANTHROPIC_API_KEY') else 'Missing'}")

# ## Input Data Loading
# Load and validate input file with trip requirements.

def load_input_file(file_path: str) -> dict:
    """Load and validate input file."""
    try:
        with open(file_path, 'r') as f:
            input_data = json.load(f)
        
        # Basic validation
        required_fields = ["trip_dates", "duration_days", "budget", "pace"]
        for field in required_fields:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Check if optional section exists, and validate accommodation_location if it does
        if "optional" in input_data and "accommodation_location" not in input_data["optional"]:
            raise ValueError("Missing required field: optional.accommodation_location")
        
        return input_data
    
    except FileNotFoundError:
        print(f"Error: Input file '{file_path}' not found.")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file: {e}")
        return None
    except ValueError as e:
        print(f"Error: {e}")
        return None

# Test with different input files
print("Available input files:")
try:
    for file in os.listdir('../inputs'):
        if file.endswith('.json'):
            print(f"  ../inputs/{file}")
except FileNotFoundError:
    print("No inputs directory found")
    
class TransportSustainabilityAgent:
    """
    Deterministic transport routing processor for Singapore travel itineraries.
    Uses Google Routes API and hardcoded filtering rules to calculate optimal
    transport options between destinations.
    """

    def __init__(self):
        """Initialize the transport agent (no state needed for deterministic processing)."""
        pass

    def calculate_day_by_day_routes(
        self,
        places_data: Dict,
        accommodation_location: Dict
    ) -> Dict:
        """
        Calculate routes day-by-day based on itinerary using deterministic Google Routes API.

        For each day:
        - Start from accommodation
        - Go to morning place (if not null)
        - Go to lunch place (if not null)
        - Go to afternoon place (if not null)
        - Skip null items and jump to next place
        - Calculate transport options for each leg using Google Routes API

        Args:
            places_data: Input data with itinerary
            accommodation_location: Dict with lat, lng of accommodation

        Returns:
            Dict with transport data organized by date with route connections
        """
        from tools import get_transport_options_concurrent
        # from tools import get_optimized_daily_route  # COMMENTED OUT: Not using waypoint optimization (It's a WIP future enhancement)

        itinerary = places_data.get("itinerary", {})
        transport = {}

        # Extract user preferences for LLM
        requirements = places_data.get("requirements", {})
        user_preferences = {
            "pace": requirements.get("pace"),
            "budget_total_sgd": requirements.get("budget_total_sgd"),
            "travelers": requirements.get("travelers"),
            "eco_preferences": requirements.get("optional", {}).get("eco_preferences"),
            "accessibility_needs": requirements.get("optional", {}).get("accessibility_needs")
        }

        logger.info(f"Calculating day-by-day routes for {len(itinerary)} days...")

        connection_id = 1

        for date, day_data in itinerary.items():
            logger.info(f"Processing day: {date}")

            # Build sequence of places for the day (skip nulls and empty arrays)
            sequence = []

            # Always start from accommodation
            acc_location = {
                "latitude": accommodation_location.get("lat"),
                "longitude": accommodation_location.get("lng") or accommodation_location.get("lon")
            }
            sequence.append({
                "name": "Accommodation",
                "location": acc_location,
                "place_id": "accommodation"
            })

            # Dynamically iterate through all time periods in the day (morning, lunch, afternoon, etc.)
            # Sort by time to ensure correct order
            time_periods = []
            for period_name, period_data in day_data.items():
                if isinstance(period_data, dict) and "time" in period_data:
                    time_periods.append((period_name, period_data))

            # Sort by time
            time_periods.sort(key=lambda x: x[1].get("time", "00:00"))

            logger.info(f"  Found {len(time_periods)} time periods for {date}: {[p[0] for p in time_periods]}")

            # Add places from each time period
            for period_name, period_data in time_periods:
                items = period_data.get("items", [])

                # Handle both array and single item cases
                if not isinstance(items, list):
                    items = [items] if items else []

                # Process each item in the period (usually just one, but handle multiple)
                for item in items:
                    if item:  # Skip null/None items
                        item_geo = item.get("geo", {})
                        if item_geo.get("latitude") and item_geo.get("longitude"):
                            sequence.append({
                                "name": item.get("name", "Unknown"),
                                "location": item_geo,
                                "place_id": item.get("place_id")
                            })
                            logger.info(f"    Added {item.get('name')} from {period_name}")

            # === ROUTE OPTIMIZATION (COMMENTED OUT) ===
            # # Optimize visit order using Google Routes API (for sequences with 3+ places)
            # optimized_sequence = sequence
            # optimization_applied = False
            #
            # if len(sequence) >= 3:
            #     logger.info(f"  Optimizing route for {len(sequence)} places using Google Routes API...")
            #     logger.info(f"  Original order: {' -> '.join([p['name'] for p in sequence])}")
            #
            #     optimization_result = get_optimized_daily_route(sequence, travel_mode="DRIVE")
            #
            #     if optimization_result:
            #         optimized_sequence = optimization_result['optimized_places']
            #         optimization_applied = True
            #
            #         logger.info(f"  Optimization successful!")
            #         logger.info(f"  Optimized order: {' -> '.join([p['name'] for p in optimized_sequence])}")
            #         logger.info(f"  Total distance: {optimization_result['total_distance_km']} km")
            #         logger.info(f"  Total duration: {optimization_result['total_duration_minutes']} min")
            #         logger.info(f"  Savings: Using deterministic Google Routes optimization")
            #     else:
            #         logger.warning(f"  Optimization failed, using original order")
            #         optimized_sequence = sequence
            # else:
            #     logger.info(f"  Skipping optimization (< 3 places in sequence)")

            # Use original chronological sequence (no optimization)
            optimized_sequence = sequence
            optimization_applied = False

            # Calculate routes for each leg (using original chronological sequence)
            connections = []
            for i in range(len(optimized_sequence) - 1):
                origin = optimized_sequence[i]
                destination = optimized_sequence[i + 1]

                logger.info(f"  Route: {origin['name']} -> {destination['name']}")

                # Call Google Routes API to get transport options
                transport_options = get_transport_options_concurrent(
                    origin=origin['location'],
                    destination=destination['location']
                )

                # Format transport modes like the old format
                transport_modes = self._format_transport_modes(transport_options)

                connection = {
                    "connection_id": connection_id,
                    "from_place_id": origin['place_id'],
                    "to_place_id": destination['place_id'],
                    "from_place_name": origin['name'],
                    "to_place_name": destination['name'],
                    "transport_modes": transport_modes
                }
                connections.append(connection)
                connection_id += 1

            # === LLM INTEGRATION === (COMMENTED OUT)
            # # 1. Intelligent Route Optimization
            # logger.info(f"  Generating LLM route optimization for {date}...")
            # route_optimization = self.optimize_daily_routes_with_llm(
            #     connections, date, user_preferences
            # )

            # # 2. Personalized Transport Recommendations
            # logger.info(f"  Generating personalized recommendations for {date}...")
            # # Determine time of day
            # time_of_day = "morning"  # Default
            # if len(connections) > 0:
            #     if morning_item:
            #         time_of_day = "morning"
            #     elif lunch_item:
            #         time_of_day = "afternoon"
            #     elif afternoon_item:
            #         time_of_day = "afternoon"

            # personalized_tips = self.generate_personalized_recommendations(
            #     connections, user_preferences, time_of_day
            # )

            # # 3. Carbon-Conscious Travel Assistant
            # logger.info(f"  Generating carbon insights for {date}...")
            # carbon_insights = self.generate_carbon_insights(
            #     connections, user_preferences.get("eco_preferences", "no")
            # )

            # Store connections WITHOUT LLM recommendations for this date
            transport[date] = {
                "connections": connections
                # "route_optimization": {
                #     "applied": optimization_applied,
                #     "method": "google_routes_optimize_waypoint_order" if optimization_applied else "none",
                #     "original_order": [p['name'] for p in sequence] if optimization_applied else None,
                #     "optimized_order": [p['name'] for p in optimized_sequence] if optimization_applied else None
                # }
                # "llm_recommendations": {
                #     "route_optimization": route_optimization,
                #     "personalized_tips": personalized_tips,
                #     "carbon_insights": carbon_insights
                # }
            }

        logger.info(f"Completed day-by-day route calculations (LLM recommendations disabled)")
        return transport

    def _format_transport_modes(self, transport_options: Dict) -> List[Dict]:
        """
        Format transport modes from Google Routes API response.

        Args:
            transport_options: Dict with transport mode data

        Returns:
            List of formatted transport mode entries
        """
        from singapore_transport_carbon_score import carbon_estimate

        transport_modes = []
        for mode, mode_data in transport_options.items():
            # Check if mode_data is None and log it
            if mode_data is None:
                logger.warning(f"mode_data is None for mode: {mode}")
                continue

            # Map API mode names to user-friendly names (standardized terminology)
            mode_map = {
                "WALK": "walk",
                "TRANSIT": "transit",
                "DRIVE": "ride",  # Changed from "drive" to "ride"
                "CYCLE": "cycle"
            }
            friendly_mode = mode_map.get(mode, mode.lower())

            # For TRANSIT mode, determine if it's mrt, bus, or public_transport
            if mode == "TRANSIT" and mode_data and "transit_summary" in mode_data:
                transit_summary = mode_data.get("transit_summary", "").lower()
                # Check if it contains both MRT and Bus
                has_mrt = "mrt" in transit_summary or "metro" in transit_summary or "train" in transit_summary
                has_bus = "bus" in transit_summary

                if has_mrt and has_bus:
                    friendly_mode = "public_transport"
                elif has_mrt:
                    friendly_mode = "mrt"
                elif has_bus:
                    friendly_mode = "bus"
                else:
                    friendly_mode = "public_transport"

            distance_km = mode_data.get("distance_km", 0)
            duration_minutes = mode_data.get("duration_minutes", 0)
            cost_sgd = mode_data.get("estimated_cost_sgd", 0.0)

            # Calculate carbon emissions using carbon_estimate
            carbon_kg = carbon_estimate(friendly_mode, distance_km)

            # Create route summary with appropriate display text
            if friendly_mode == "ride":
                route_summary_text = "Grab/Private Hire/Taxi"
            else:
                route_summary_text = friendly_mode
            route_summary = f"{distance_km} km, {duration_minutes:.0f} mins via {route_summary_text}"

            transport_mode_entry = {
                "mode": friendly_mode,
                "distance_km": distance_km,
                "duration_minutes": round(duration_minutes, 1),
                "cost_sgd": round(cost_sgd, 2),
                "carbon_kg": round(carbon_kg, 3),
                "route_summary": route_summary
            }

            # Add transit summary if available (for all transit modes)
            if mode == "TRANSIT" and mode_data and "transit_summary" in mode_data:
                transport_mode_entry["transit_summary"] = mode_data["transit_summary"]
                transport_mode_entry["num_transfers"] = mode_data.get("num_transfers", 0)

            # Add note for cycle (custom category)
            if mode == "CYCLING":
                transport_mode_entry["note"] = mode_data.get("note", "")

            transport_modes.append(transport_mode_entry)

        return transport_modes

    # def optimize_daily_routes_with_llm(
#         self,
#         connections: List[Dict],
#         date: str,
#         user_preferences: Dict
#     ) -> Dict:
#         """
#         Use LLM to analyze all connections for a day and provide intelligent recommendations.

#         Args:
#             connections: List of connection dicts with transport modes
#             date: Date string (e.g., "2025-06-01")
#             user_preferences: User preferences from input (pace, budget, eco_preferences, etc.)

#         Returns:
#             Dict with:
#             - recommended_modes: List of recommended transport mode per connection
#             - rationale: Explanation for recommendations
#             - optimization_summary: Overall summary of the day's transport
#         """
#         if not connections:
#             return {
#                 "recommended_modes": [],
#                 "rationale": "No connections to optimize",
#                 "optimization_summary": "No travel required for this day"
#             }

#         # Prepare data for LLM
#         connections_summary = []
#         for conn in connections:
#             modes_summary = []
#             for mode_data in conn.get("transport_modes", []):
#                 modes_summary.append({
#                     "mode": mode_data["mode"],
#                     "distance_km": mode_data["distance_km"],
#                     "duration_minutes": mode_data["duration_minutes"],
#                     "cost_sgd": mode_data["cost_sgd"],
#                     "carbon_kg": mode_data["carbon_kg"]
#                 })

#             connections_summary.append({
#                 "connection_id": conn["connection_id"],
#                 "from": conn["from_place_name"],
#                 "to": conn["to_place_name"],
#                 "available_modes": modes_summary
#             })

#         # Extract user preferences
#         pace = user_preferences.get("pace")
#         budget_sgd = user_preferences.get("budget_total_sgd")
#         eco_preferences = user_preferences.get("eco_preferences")
#         travelers = user_preferences.get("travelers")
#         adults = travelers.get("adults")
#         children = travelers.get("children")

#         prompt = f"""You are a Singapore travel optimization expert. Analyze this day's transport connections and recommend the best transport mode for each leg.

# **Date:** {date}

# **Traveler Profile:**
# - Travel pace: {pace}
# - Budget: ${budget_sgd} SGD total
# - Eco-conscious: {eco_preferences}
# - Group: {adults} adult(s), {children} children

# **Connections for the day:**
# {json.dumps(connections_summary, indent=2)}

# **Your Task:**
# For each connection, recommend the BEST transport mode considering:
# 1. Time efficiency (especially for {pace} pace)
# 2. Cost effectiveness (total budget: ${budget_sgd})
# 3. Carbon footprint ({'high priority' if eco_preferences == 'yes' else 'considered'})
# 4. Family-friendliness ({'important' if children > 0 else 'not applicable'})
# 5. Practicality (walking distance, transfers, comfort)

# **Output Format (JSON only, no markdown):**
# {{
#     "recommended_modes": [
#         {{
#             "connection_id": 1,
#             "recommended_mode": "walking",
#             "reason": "Short distance (0.9km), saves money, eco-friendly, good for {pace} pace"
#         }}
#     ],
#     "optimization_summary": "Brief summary of the day's transport strategy (2-3 sentences)",
#     "total_estimated_cost": 0.00,
#     "total_carbon_saved": 0.5,
#     "time_optimization_notes": "Any time-saving tips or warnings"
# }}
# """

#         try:
#             response = self.client.chat.completions.create(
#                 model=self.model_name,
#                 temperature=0.3,
#                 messages=[
#                     {"role": "system", "content": "You are a Singapore travel transport optimization expert. Provide practical, cost-effective, and sustainable transport recommendations."},
#                     {"role": "user", "content": prompt}
#                 ]
#             )

#             llm_output = response.choices[0].message.content.strip()

#             # Handle markdown-wrapped JSON
#             if '```json' in llm_output:
#                 import re
#                 pattern = r'```json\s*(.*?)\s*```'
#                 match = re.search(pattern, llm_output, re.DOTALL)
#                 if match:
#                     llm_output = match.group(1).strip()
#             elif llm_output.startswith('```') and llm_output.endswith('```'):
#                 lines = llm_output.split('\n')
#                 if lines[0].startswith('```'):
#                     lines = lines[1:]
#                 if lines[-1] == '```':
#                     lines = lines[:-1]
#                 llm_output = '\n'.join(lines).strip()

#             result = json.loads(llm_output)
#             logger.info(f"LLM route optimization completed for {date}")
#             return result

#         except Exception as e:
#             logger.error(f"LLM optimization error for {date}: {e}")
#             return {
#                 "recommended_modes": [],
#                 "rationale": f"Optimization unavailable: {str(e)}",
#                 "optimization_summary": "Unable to optimize routes"
#             }

#     def generate_personalized_recommendations(
#         self,
#         connections: List[Dict],
#         user_preferences: Dict,
#         time_of_day: str = "morning"
#     ) -> List[str]:
#         """
#         Generate personalized transport recommendations based on context.

#         Args:
#             connections: List of connection dicts
#             user_preferences: User preferences
#             time_of_day: "morning", "afternoon", "evening"

#         Returns:
#             List of contextual recommendation strings
#         """
#         if not connections:
#             return []

#         # Extract key preferences
#         travelers = user_preferences.get("travelers", {})
#         children = travelers.get("children", 0)
#         accessibility = user_preferences.get("accessibility_needs", "no_preference")

#         prompt = f"""You are a Singapore travel expert. Provide 3-5 SHORT, practical transport tips for these travelers.

# **Context:**
# - Time: {time_of_day}
# - Travelers: {travelers.get('adults', 1)} adult(s), {children} children
# - Accessibility: {accessibility}
# - Total connections today: {len(connections)}

# **Provide practical tips like:**
# - "Avoid rush hour (7-9 AM, 5-7 PM) for smoother MRT travel"
# - "Book GrabCar in advance during afternoon peak hours"
# - "Bring an umbrella - afternoon rain is common in Singapore"
# - "MRT stations have elevators - good for families with strollers"
# - "Walking between close attractions saves time vs. waiting for transport"

# **Output (JSON array of strings, 3-5 tips):**
# ["tip 1", "tip 2", "tip 3"]
# """

#         try:
#             response = self.client.chat.completions.create(
#                 model=self.model_name,
#                 temperature=0.4,
#                 messages=[
#                     {"role": "system", "content": "You are a practical Singapore travel advisor. Give SHORT, actionable tips."},
#                     {"role": "user", "content": prompt}
#                 ]
#             )

#             llm_output = response.choices[0].message.content.strip()

#             # Handle markdown-wrapped JSON
#             if '```json' in llm_output:
#                 import re
#                 pattern = r'```json\s*(.*?)\s*```'
#                 match = re.search(pattern, llm_output, re.DOTALL)
#                 if match:
#                     llm_output = match.group(1).strip()
#             elif llm_output.startswith('```') and llm_output.endswith('```'):
#                 lines = llm_output.split('\n')
#                 lines = [l for l in lines if not l.strip().startswith('```')]
#                 llm_output = '\n'.join(lines).strip()

#             tips = json.loads(llm_output)
#             logger.info(f"Generated {len(tips)} personalized recommendations")
#             return tips

#         except Exception as e:
#             logger.error(f"Error generating personalized recommendations: {e}")
#             return ["Plan ahead for smoother travel", "Check MRT schedules before departure"]

#     def generate_carbon_insights(
#         self,
#         connections: List[Dict],
#         eco_preference: str = "no"
#     ) -> Dict:
#         """
#         Generate carbon-conscious travel insights and recommendations.

#         Args:
#             connections: List of connection dicts with carbon data
#             eco_preference: User's eco preference ("yes", "no")

#         Returns:
#             Dict with carbon insights and eco-friendly suggestions
#         """
#         if not connections:
#             return {
#                 "total_carbon_kg": 0.0,
#                 "eco_insights": [],
#                 "carbon_savings_opportunities": []
#             }

#         # Calculate total carbon for current recommendations
#         total_carbon = 0.0
#         carbon_by_mode = {}

#         for conn in connections:
#             for mode_data in conn.get("transport_modes", []):
#                 mode = mode_data["mode"]
#                 carbon = mode_data["carbon_kg"]

#                 if mode not in carbon_by_mode:
#                     carbon_by_mode[mode] = {"count": 0, "total_carbon": 0.0, "total_distance": 0.0}

#                 carbon_by_mode[mode]["count"] += 1
#                 carbon_by_mode[mode]["total_carbon"] += carbon
#                 carbon_by_mode[mode]["total_distance"] += mode_data["distance_km"]

#         # Prepare summary for LLM
#         connections_carbon = []
#         for conn in connections:
#             modes_carbon = []
#             for mode_data in conn.get("transport_modes", []):
#                 modes_carbon.append({
#                     "mode": mode_data["mode"],
#                     "carbon_kg": mode_data["carbon_kg"],
#                     "distance_km": mode_data["distance_km"]
#                 })

#             connections_carbon.append({
#                 "from": conn["from_place_name"],
#                 "to": conn["to_place_name"],
#                 "modes": modes_carbon
#             })

#         prompt = f"""You are a carbon footprint expert for Singapore travel. Analyze these transport connections and provide eco-friendly insights.

# **Eco-conscious traveler:** {eco_preference}

# **Today's connections:**
# {json.dumps(connections_carbon, indent=2)}

# **Provide:**
# 1. Total carbon footprint estimate (sum lowest-carbon option for each leg)
# 2. 2-3 specific eco-friendly suggestions (e.g., "Walk 0.9km instead of taxi to save 0.25kg CO₂")
# 3. Carbon comparison (e.g., "Taking MRT instead of taxi all day saves 2.1kg CO₂ (equivalent to X)")

# **Output (JSON only):**
# {{
#     "total_carbon_kg": 0.5,
#     "eco_insights": [
#         "Walking short distances (<1km) eliminates 0.3kg CO₂ today",
#         "Public transport reduces carbon by 60% vs. taxis"
#     ],
#     "carbon_savings_opportunities": [
#         {{
#         "connection": "Accommodation → Morning place",
#         "suggestion": "Walk instead of taxi",
#         "carbon_saved_kg": 0.25,
#         "time_added_minutes": 8
#         }}
#     ],
#     "carbon_equivalent": "Today's eco-friendly choices save carbon equal to charging 50 smartphones"
# }}
# """

#         try:
#             response = self.client.chat.completions.create(
#                 model=self.model_name,
#                 temperature=0.3,
#                 messages=[
#                     {"role": "system", "content": "You are a carbon footprint expert. Provide accurate, practical eco-friendly travel advice."},
#                     {"role": "user", "content": prompt}
#                 ]
#             )

#             llm_output = response.choices[0].message.content.strip()

#             # Handle markdown-wrapped JSON
#             if '```json' in llm_output:
#                 import re
#                 pattern = r'```json\s*(.*?)\s*```'
#                 match = re.search(pattern, llm_output, re.DOTALL)
#                 if match:
#                     llm_output = match.group(1).strip()
#             elif llm_output.startswith('```') and llm_output.endswith('```'):
#                 lines = llm_output.split('\n')
#                 lines = [l for l in lines if not l.strip().startswith('```')]
#                 llm_output = '\n'.join(lines).strip()

#             result = json.loads(llm_output)
#             logger.info(f"Generated carbon insights")
#             return result

#         except Exception as e:
#             logger.error(f"Error generating carbon insights: {e}")
#             return {
#                 "total_carbon_kg": 0.0,
#                 "eco_insights": ["Consider walking or public transport for short distances"],
#                 "carbon_savings_opportunities": []
#             }

    def format_output(self, transport_data: Dict, places_data: Dict) -> Dict:
        """
        Format final output with all transport and carbon data.

        NEW FORMAT: Copy input JSON and append transport section with dates from itinerary.

        Args:
            transport_data: Dict with transport data organized by date
            places_data: Original places data with requirements, retrieval, and itinerary

        Returns:
            Formatted output dict: input + transport section with dates
        """
        # Copy input data wholesale, then append transport section
        import copy
        output = copy.deepcopy(places_data)
        output["transport"] = transport_data

        return output


def process_transport_data(input_file: str, output_file: str, accommodation_location: Optional[Dict] = None):
    """
    Main function to process places data and calculate transport options.

    Args:
        input_file: Path to input JSON file with places data
        output_file: Path to output JSON file
        accommodation_location: Optional accommodation location dict
    """
    import json
    import time
    from tools import clear_raw_responses, dump_raw_responses

    start_time = time.time()

    # Clear any previous raw responses
    clear_raw_responses()
    logger.info("Cleared previous raw Google Maps responses")

    # Load input data
    logger.info(f"Loading input file: {input_file}")
    try:
        with open(input_file, 'r') as f:
            places_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load input file: {e}")
        return {'error': f"Failed to load input file: {str(e)}"}

    # Extract accommodation location from input file if not provided
    if accommodation_location is None:
        optional = places_data.get("requirements", {}).get("optional", {})
        input_accommodation = optional.get("accommodation_location", {})
        if input_accommodation:
            accommodation_location = {
                "lat": input_accommodation.get("lat"),
                "lng": input_accommodation.get("lng") or input_accommodation.get("lon")
            }
            logger.info(f"Using accommodation location from input file: {accommodation_location}")

    # Initialize agent
    logger.info("Initializing Transport Sustainability Agent")
    agent = TransportSustainabilityAgent()

    # Calculate day-by-day routes based on itinerary
    logger.info("Calculating day-by-day routes...")
    transport_data = agent.calculate_day_by_day_routes(places_data, accommodation_location)

    # Format output
    logger.info("Formatting output...")
    output = agent.format_output(transport_data, places_data)

    # Add timing info
    elapsed_time = time.time() - start_time
    output["processing_time_seconds"] = round(elapsed_time, 2)

    # Save output
    logger.info(f"Saving output to: {output_file}")
    try:
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        logger.info(f"Successfully saved output")
    except Exception as e:
        logger.error(f"Failed to save output: {e}")
        return {'error': f"Failed to save output: {str(e)}"}

    # Dump raw Google Maps responses
    raw_output_file = output_file.replace(".json", "_raw_responses.json")
    dump_raw_responses(raw_output_file)

    # Calculate total connections
    total_connections = sum(len(day_data.get("connections", [])) for day_data in transport_data.values())

    # Print summary if not running in Lambda
    if not os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
        print(f"\n{'='*80}")
        print(f"TRANSPORT PROCESSING COMPLETE")
        print(f"{'='*80}")
        print(f"Days processed: {len(transport_data)}")
        print(f"Total routes calculated: {total_connections}")
        print(f"Processing time: {elapsed_time:.2f}s")
        print(f"Output saved to: {output_file}")
        print(f"Raw Google Maps responses: {raw_output_file}")
        print(f"{'='*80}\n")

    # Return success with metadata
    return {
        'days_processed': len(transport_data),
        'total_connections': total_connections,
        'processing_time_seconds': elapsed_time
    }


# Main execution
if __name__ == "__main__":
    import sys

    # Check if input file provided
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_file> [output_file] [--accommodation lat,lon]")
        print("\nExample:")
        print("  python main.py inputs/attractions_12_food_4.json output.json --accommodation 1.3294,103.8021")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "transport_output.json"

    # Parse accommodation location if provided
    accommodation = None
    if "--accommodation" in sys.argv:
        acc_idx = sys.argv.index("--accommodation")
        if acc_idx + 1 < len(sys.argv):
            acc_coords = sys.argv[acc_idx + 1].split(",")
            if len(acc_coords) == 2:
                try:
                    accommodation = {
                        "lat": float(acc_coords[0]),
                        "lon": float(acc_coords[1])
                    }
                    print(f"Using accommodation location: {accommodation}")
                except ValueError:
                    print("Warning: Invalid accommodation coordinates, ignoring")

    # Process transport data
    process_transport_data(input_file, output_file, accommodation)