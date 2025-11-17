"""
Enhanced Transport Tools for Google Routes API Integration
- TWO_WHEELER not used (motorbikes not relevant for tourists)
- Converts walking >2km to cycling category
- Creates transit route summaries
"""

import requests
import time
import logging
import threading
import json
import os
from typing import Dict, List, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import (
    GOOGLE_MAPS_API_KEY,
    GOOGLE_ROUTES_API_URL,
    CONCURRENT_CONFIG,
    TRANSPORT_THRESHOLDS,
    estimate_taxi_cost
)

logger = logging.getLogger(__name__)

# Rate limiting for API calls
_rate_limit_lock = threading.Lock()
_last_request_time = {"time": 0}
_min_delay_between_requests = 0.5  # 500ms between requests

# Store raw Google Maps responses for debugging
_raw_responses = []


def compute_route(
    origin: Dict[str, float],
    destination: Dict[str, float],
    travel_mode: str,
    language: str = "en"
) -> Optional[Dict[str, Any]]:
    """
    Call Google Routes API v2 to compute route between two locations.

    Args:
        origin: Dict with 'latitude' and 'longitude' keys
        destination: Dict with 'latitude' and 'longitude' keys
        travel_mode: One of 'DRIVE', 'TRANSIT', 'WALK'
        language: Language code for response

    Returns:
        Route data dict or None if failed
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.error("GOOGLE_MAPS_API_KEY not set")
        return None

    # Prepare request body
    request_body = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": origin["latitude"],
                    "longitude": origin["longitude"]
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": destination["latitude"],
                    "longitude": destination["longitude"]
                }
            }
        },
        "travelMode": travel_mode,
        "computeAlternativeRoutes": False,
        "languageCode": language,
        "units": "METRIC"
    }

    # Only add routing preference for DRIVE mode (not allowed for WALK, TRANSIT)
    if travel_mode == "DRIVE":
        request_body["routingPreference"] = "TRAFFIC_AWARE"
        # request_body["routingPreference"] = "TRAFFIC_AWARE_OPTIMAL"
        # request_body["computeAlternativeRoutes"] = True
        request_body["routeModifiers"] = {
            "avoidTolls": False,
            "avoidHighways": False,
            "avoidFerries": False
        }

    # Set headers
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.legs,routes.polyline"
    }

    # Apply rate limiting
    with _rate_limit_lock:
        elapsed = time.time() - _last_request_time["time"]
        if elapsed < _min_delay_between_requests:
            sleep_time = _min_delay_between_requests - elapsed
            time.sleep(sleep_time)
        _last_request_time["time"] = time.time()

    try:
        logger.info(f"Making API request for {travel_mode} mode")
        response = requests.post(
            GOOGLE_ROUTES_API_URL,
            json=request_body,
            headers=headers,
            timeout=CONCURRENT_CONFIG["timeout_seconds"]
        )

        logger.info(f"API response status: {response.status_code} for {travel_mode}")

        if response.status_code == 200:
            data = response.json()

            # Store raw response for debugging
            _raw_responses.append({
                "travel_mode": travel_mode,
                "origin": origin,
                "destination": destination,
                "response": data,
                "timestamp": time.time()
            })

            if "routes" in data and len(data["routes"]) > 0:
                logger.info(f"Successfully retrieved route for {travel_mode}")
                return data["routes"][0]
            else:
                logger.warning(f"No routes found for {travel_mode}. Response: {data}")
                return None
        else:
            logger.error(f"Routes API error {response.status_code} for {travel_mode}")
            logger.error(f"Response body: {response.text[:500]}")  # First 500 chars
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception for {travel_mode}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error for {travel_mode}: {e}")
        return None


def create_transit_summary(transit_steps: List[Dict]) -> str:
    """
    Create human-readable transit summary from transit steps.

    Example: "Take MRT Red Line to Raffles, then Bus 174 to destination"

    Args:
        transit_steps: List of transit step dicts with 'line' and 'vehicle'

    Returns:
        Human-readable summary string
    """
    if not transit_steps:
        return "Direct public transport"

    summary_parts = []
    for i, step in enumerate(transit_steps):
        line_name = step.get("line", "Unknown")
        vehicle_type = step.get("vehicle", "Unknown").lower()

        # Simplify vehicle type names
        if "subway" in vehicle_type or "metro" in vehicle_type or "mrt" in vehicle_type.lower():
            vehicle = "MRT"
        elif "bus" in vehicle_type:
            vehicle = "Bus"
        elif "train" in vehicle_type:
            vehicle = "Train"
        else:
            vehicle = vehicle_type.capitalize()

        if i == 0:
            summary_parts.append(f"Take {vehicle} {line_name}")
        else:
            summary_parts.append(f"then {vehicle} {line_name}")

    return ", ".join(summary_parts)


def parse_route_data(route: Dict[str, Any], travel_mode: str) -> Dict[str, Any]:
    """
    Parse Google Routes API response into standardized format.

    - Creates cycling category for walking >2km
    - Adds transit summary
    - Includes raw transit steps for reference

    Args:
        route: Route data from API
        travel_mode: Travel mode used

    Returns:
        Parsed route data dict
    """
    if not route:
        return None

    try:
        # Extract basic info
        distance_meters = route.get("distanceMeters", 0)
        distance_km = distance_meters / 1000.0

        logger.info(f"Parsing {travel_mode}: distance_meters={distance_meters}, distance_km={distance_km}")

        # Parse duration (format: "123s")
        duration_str = route.get("duration", "0s")
        duration_seconds = int(duration_str.rstrip("s"))
        duration_minutes = duration_seconds / 60.0

        logger.info(f"Parsing {travel_mode}: duration={duration_seconds}s ({duration_minutes}min)")

        # Get legs info (contains steps, transfers, etc.)
        legs = route.get("legs", [])

        # Count transfers for transit
        num_transfers = 0
        transit_steps = []
        walking_distance_m = 0

        if legs:
            for leg in legs:
                steps = leg.get("steps", [])
                for step in steps:
                    travel_mode_step = step.get("travelMode", "")
                    if travel_mode_step == "TRANSIT":
                        transit_detail = step.get("transitDetails", {})
                        transit_steps.append({
                            "line": transit_detail.get("transitLine", {}).get("name", "Unknown"),
                            "vehicle": transit_detail.get("transitLine", {}).get("vehicle", {}).get("type", "Unknown")
                        })
                    elif travel_mode_step == "WALK":
                        walking_distance_m += step.get("distanceMeters", 0)

            # Transfers = number of transit segments - 1
            if len(transit_steps) > 0:
                num_transfers = len(transit_steps) - 1

        result = {
            "travel_mode": travel_mode,
            "distance_km": round(distance_km, 2),
            "distance_meters": distance_meters,
            "duration_minutes": round(duration_minutes, 1),
            "duration_seconds": duration_seconds,
        }

        # Add transit-specific data with summary
        if travel_mode == "TRANSIT":
            result["num_transfers"] = num_transfers
            result["transit_steps"] = transit_steps
            result["transit_summary"] = create_transit_summary(transit_steps)
            result["walking_distance_km"] = round(walking_distance_m / 1000.0, 2)

        # Estimate cost
        if travel_mode == "DRIVE":
            result["estimated_cost_sgd"] = estimate_taxi_cost(distance_km, duration_minutes)
        elif travel_mode == "TRANSIT":
            # Use simple MRT estimate
            result["estimated_cost_sgd"] = round(0.92 + (distance_km * 0.12), 2)
        else:
            result["estimated_cost_sgd"] = 0.0

        return result

    except Exception as e:
        logger.error(f"Error parsing route data: {e}")
        return None


def convert_walking_to_cycling(walking_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert walking route to cycling estimate.

    Cycling assumptions:
    - Average speed: 15 km/h (leisurely pace)
    - Duration = distance / speed
    - No cost
    - Max distance capped at 8km (enforced by caller)

    Args:
        walking_data: Walking route data

    Returns:
        Cycling route data (estimated, not from API)
    """
    distance_km = walking_data.get("distance_km", 0)

    # Estimate cycling duration (15 km/h average)
    cycling_speed_kmh = 15.0
    duration_hours = distance_km / cycling_speed_kmh
    duration_minutes = duration_hours * 60

    return {
        "travel_mode": "CYCLE",
        "distance_km": distance_km,
        "distance_meters": walking_data.get("distance_meters", 0),
        "duration_minutes": round(duration_minutes, 1),
        "duration_seconds": int(duration_minutes * 60),
        "estimated_cost_sgd": 0.0,
        "note": "Estimated based on walking route (not from Google API)"
    }


def get_transport_options_concurrent(
    origin: Dict[str, float],
    destination: Dict[str, float],
    modes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get transport options for all modes concurrently (parallel API calls).

    - Walking >2km converted to cycling
    - Walking <=5km still shown

    Args:
        origin: Dict with 'latitude' and 'longitude' keys
        destination: Dict with 'latitude' and 'longitude' keys
        modes: List of modes to check (default: DRIVE, TRANSIT, WALK)

    Returns:
        Dict mapping mode names to route data
    """
    if modes is None:
        modes = ["DRIVE", "TRANSIT", "WALK"]  # TWO_WHEELER removed

    results = {}

    def fetch_mode(mode: str) -> Tuple[str, Optional[Dict]]:
        """Helper function to fetch a single mode."""
        route = compute_route(origin, destination, mode)
        parsed = parse_route_data(route, mode)
        return (mode, parsed)

    # Use ThreadPoolExecutor for concurrent API calls
    with ThreadPoolExecutor(max_workers=min(len(modes), CONCURRENT_CONFIG["max_workers"])) as executor:
        # Submit all tasks
        futures = {executor.submit(fetch_mode, mode): mode for mode in modes}

        # Collect results as they complete
        for future in as_completed(futures):
            try:
                mode, parsed = future.result()
                if parsed:
                    results[mode] = parsed
                    logger.info(f"Successfully fetched route for {mode}")
                else:
                    logger.warning(f"No route data for {mode}")
            except Exception as e:
                mode = futures[future]
                logger.error(f"Error fetching route for {mode}: {e}")

    # Process walking results with new logic:
    # 1. Cap walking at 10km (API level should already do this, but enforce here)
    # 2. If >2km: convert to cycling and REMOVE walk from output
    # 3. If <=2km: keep walk only
    # 4. Cap cycling at 8km max
    if "WALK" in results:
        walking_data = results["WALK"]
        distance_km = walking_data.get("distance_km", 0)
        duration_minutes = walking_data.get("duration_minutes", 0)

        walk_thresholds = TRANSPORT_THRESHOLDS["walk"]
        cycle_thresholds = TRANSPORT_THRESHOLDS["cycle"]

        # Enforce 10km walking cap
        if distance_km > walk_thresholds["api_max_distance_km"]:
            logger.info(f"Removing walking option ({distance_km}km > {walk_thresholds['api_max_distance_km']}km max)")
            del results["WALK"]
            return results

        # Check if we should create cycling option (>2km or >20min)
        should_convert_to_cycle = (
            distance_km > walk_thresholds["convert_to_cycle_distance_km"] or
            duration_minutes > walk_thresholds["convert_to_cycle_duration_minutes"]
        )

        if should_convert_to_cycle:
            # Only create cycling option if within 8km cycle cap
            if distance_km <= cycle_thresholds["max_distance_km"]:
                cycling_data = convert_walking_to_cycling(walking_data)
                results["CYCLE"] = cycling_data
                logger.info(f"Created cycling option for {distance_km}km / {duration_minutes}min route")

                # ALWAYS remove walk from output when >2km (converted to cycle)
                logger.info(f"Removing walking option ({distance_km}km > {walk_thresholds['convert_to_cycle_distance_km']}km)")
                del results["WALK"]
            else:
                # Distance exceeds cycling cap, remove walking (no viable active transport)
                logger.info(f"Distance {distance_km}km exceeds cycling max {cycle_thresholds['max_distance_km']}km, removing walk option")
                del results["WALK"]

    return results




def dump_raw_responses(output_file: str = "TransportAgent/transport_response.json"):
    """
    Dump all raw Google Maps API responses to JSON file for debugging.

    Args:
        output_file: Path to output file
    """
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump({
                "total_requests": len(_raw_responses),
                "responses": _raw_responses
            }, f, indent=2)
        logger.info(f"Dumped {len(_raw_responses)} raw Google Maps responses to {output_file}")
    except Exception as e:
        logger.error(f"Failed to dump raw responses: {e}")


def clear_raw_responses():
    """Clear stored raw responses (call at start of new run)"""
    global _raw_responses
    _raw_responses = []

# COMMENTED OUT: Waypoint optimization not currently used
# def compute_optimized_route(
#     origin: Dict[str, float],
#     destination: Dict[str, float],
#     intermediates: List[Dict[str, float]],
#     travel_mode: str = "DRIVE",
#     language: str = "en"
# ) -> Optional[Dict[str, Any]]:
#     """
#     Call Google Routes API v2 with waypoint optimization.
# 
#     This function uses optimizeWaypointOrder to let Google reorder the intermediate
#     waypoints for the most efficient route.
# 
#     Args:
#         origin: Dict with 'latitude' and 'longitude' keys
#         destination: Dict with 'latitude' and 'longitude' keys
#         intermediates: List of waypoint dicts with 'latitude' and 'longitude' keys
#         travel_mode: One of 'DRIVE', 'TRANSIT', 'WALK' (default: 'DRIVE')
#         language: Language code for response
# 
#     Returns:
#         Dict with:
#         - route: Route data from API
#         - optimized_waypoint_order: List of indices showing optimized order
#         - total_distance_km: Total distance in km
#         - total_duration_minutes: Total duration in minutes
#     """
#     if not GOOGLE_MAPS_API_KEY:
#         logger.error("GOOGLE_MAPS_API_KEY not set")
#         return None
# 
#     if not intermediates:
#         logger.warning("No intermediates provided, use compute_route instead")
#         return None
# 
#     # Prepare request body with intermediates
#     request_body = {
#         "origin": {
#             "location": {
#                 "latLng": {
#                     "latitude": origin["latitude"],
#                     "longitude": origin["longitude"]
#                 }
#             }
#         },
#         "destination": {
#             "location": {
#                 "latLng": {
#                     "latitude": destination["latitude"],
#                     "longitude": destination["longitude"]
#                 }
#             }
#         },
#         "intermediates": [
#             {
#                 "location": {
#                     "latLng": {
#                         "latitude": waypoint["latitude"],
#                         "longitude": waypoint["longitude"]
#                     }
#                 }
#             }
#             for waypoint in intermediates
#         ],
#         "travelMode": travel_mode,
#         "optimizeWaypointOrder": True,  # Enable optimization
#         "computeAlternativeRoutes": False,
#         "languageCode": language,
#         "units": "METRIC"
#     }
# 
#     # Add routing preferences for DRIVE mode
#     if travel_mode == "DRIVE":
#         request_body["routingPreference"] = "TRAFFIC_AWARE"
#         request_body["routeModifiers"] = {
#             "avoidTolls": False,
#             "avoidHighways": False,
#             "avoidFerries": False
#         }
# 
#     # Set headers - request optimized intermediate waypoint order in response
#     headers = {
#         "Content-Type": "application/json",
#         "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
#         "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.legs,routes.polyline,routes.optimizedIntermediateWaypointIndex"
#     }
# 
#     # Apply rate limiting
#     with _rate_limit_lock:
#         elapsed = time.time() - _last_request_time["time"]
#         if elapsed < _min_delay_between_requests:
#             sleep_time = _min_delay_between_requests - elapsed
#             time.sleep(sleep_time)
#         _last_request_time["time"] = time.time()
# 
#     try:
#         logger.info(f"Making optimized route API request for {travel_mode} with {len(intermediates)} waypoints")
#         response = requests.post(
#             GOOGLE_ROUTES_API_URL,
#             json=request_body,
#             headers=headers,
#             timeout=CONCURRENT_CONFIG["timeout_seconds"]
#         )
# 
#         logger.info(f"Optimized route API response status: {response.status_code}")
# 
#         if response.status_code == 200:
#             data = response.json()
# 
#             # Store raw response for debugging
#             _raw_responses.append({
#                 "travel_mode": travel_mode,
#                 "origin": origin,
#                 "destination": destination,
#                 "intermediates_count": len(intermediates),
#                 "optimized": True,
#                 "response": data,
#                 "timestamp": time.time()
#             })
# 
#             if "routes" in data and len(data["routes"]) > 0:
#                 route = data["routes"][0]
# 
#                 # Extract optimized waypoint order (if available)
#                 optimized_order = route.get("optimizedIntermediateWaypointIndex", list(range(len(intermediates))))
# 
#                 # Calculate total distance and duration
#                 distance_meters = route.get("distanceMeters", 0)
#                 distance_km = distance_meters / 1000.0
# 
#                 duration_str = route.get("duration", "0s")
#                 duration_seconds = int(duration_str.rstrip("s"))
#                 duration_minutes = duration_seconds / 60.0
# 
#                 logger.info(f"Successfully retrieved optimized route: {distance_km:.2f}km, {duration_minutes:.1f}min")
#                 logger.info(f"Optimized waypoint order: {optimized_order}")
# 
#                 return {
#                     "route": route,
#                     "optimized_waypoint_order": optimized_order,
#                     "total_distance_km": round(distance_km, 2),
#                     "total_duration_minutes": round(duration_minutes, 1),
#                     "travel_mode": travel_mode
#                 }
#             else:
#                 logger.warning(f"No routes found in optimized route response. Response: {data}")
#                 return None
#         else:
#             logger.error(f"Routes API error {response.status_code} for optimized route")
#             logger.error(f"Response body: {response.text[:500]}")
#             return None
# 
#     except requests.exceptions.RequestException as e:
#         logger.error(f"Request exception for optimized route: {e}")
#         return None
#     except Exception as e:
#         logger.error(f"Unexpected error for optimized route: {e}")
#         return None
# 
# 
# def get_optimized_daily_route(
#     places: List[Dict[str, Any]],
#     travel_mode: str = "DRIVE"
# ) -> Optional[Dict[str, Any]]:
#     """
#     Get optimized route for a full day's itinerary.
# 
#     Takes a list of places (with first as origin, last as destination, rest as waypoints)
#     and returns the optimized order to visit them.
# 
#     Args:
#         places: List of place dicts, each with 'name' and 'location' (lat/lng)
#                 First place is origin, last is destination, rest are waypoints
#         travel_mode: Travel mode to use (default: DRIVE)
# 
#     Returns:
#         Dict with:
#         - optimized_order: List of place indices in optimized visit order
#         - optimized_places: List of places in optimized order
#         - total_distance_km: Total distance
#         - total_duration_minutes: Total duration
#         - route_data: Full route data from API
#     """
#     if len(places) < 2:
#         logger.error("Need at least 2 places (origin and destination)")
#         return None
# 
#     # Extract origin, destination, and intermediates
#     origin_place = places[0]
#     destination_place = places[-1]
#     intermediate_places = places[1:-1] if len(places) > 2 else []
# 
#     origin = origin_place["location"]
#     destination = destination_place["location"]
#     intermediates = [place["location"] for place in intermediate_places]
# 
#     if not intermediates:
#         logger.info("No intermediates, using standard point-to-point routing")
#         route = compute_route(origin, destination, travel_mode)
#         if route:
#             distance_km = route.get("distanceMeters", 0) / 1000.0
#             duration_str = route.get("duration", "0s")
#             duration_minutes = int(duration_str.rstrip("s")) / 60.0
# 
#             return {
#                 "optimized_order": [0, 1],  # Just origin and destination
#                 "optimized_places": [origin_place, destination_place],
#                 "total_distance_km": round(distance_km, 2),
#                 "total_duration_minutes": round(duration_minutes, 1),
#                 "route_data": route
#             }
#         return None
# 
#     # Call optimized route API
#     result = compute_optimized_route(origin, destination, intermediates, travel_mode)
# 
#     if not result:
#         return None
# 
#     # Map optimized waypoint indices back to original place indices
#     optimized_waypoint_order = result["optimized_waypoint_order"]
# 
#     # Reconstruct the full optimized place order
#     # Origin (index 0) stays first, destination (index -1) stays last
#     # Intermediates are reordered based on API response
#     optimized_order = [0]  # Start with origin
#     for waypoint_idx in optimized_waypoint_order:
#         # waypoint_idx refers to position in intermediates array
#         # Map back to original places array (offset by 1 since origin is index 0)
#         original_idx = waypoint_idx + 1
#         optimized_order.append(original_idx)
#     optimized_order.append(len(places) - 1)  # End with destination
# 
#     # Create optimized places list
#     optimized_places = [places[idx] for idx in optimized_order]
# 
#     logger.info(f"Optimized visit order: {' -> '.join([p['name'] for p in optimized_places])}")
# 
#     return {
#         "optimized_order": optimized_order,
#         "optimized_places": optimized_places,
#         "total_distance_km": result["total_distance_km"],
#         "total_duration_minutes": result["total_duration_minutes"],
#         "route_data": result["route"]
#     }
