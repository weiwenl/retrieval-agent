"""
Test script for Google Routes API waypoint optimization.

This script demonstrates the new optimized routing feature that uses
Google's optimizeWaypointOrder to reorder waypoints for the most efficient route.
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from tools import get_optimized_daily_route, compute_optimized_route
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_singapore_attractions_optimization():
    """
    Test route optimization with popular Singapore attractions.

    Scenario: Starting from Marina Bay Sands, visiting multiple attractions,
    and returning to Marina Bay Sands.
    """

    # Define places (Singapore attractions)
    places = [
        {
            "name": "Marina Bay Sands (Start)",
            "location": {
                "latitude": 1.2834,
                "longitude": 103.8607
            }
        },
        {
            "name": "Gardens by the Bay",
            "location": {
                "latitude": 1.2816,
                "longitude": 103.8636
            }
        },
        {
            "name": "Singapore Flyer",
            "location": {
                "latitude": 1.2894,
                "longitude": 103.8631
            }
        },
        {
            "name": "Merlion Park",
            "location": {
                "latitude": 1.2868,
                "longitude": 103.8545
            }
        },
        {
            "name": "Chinatown",
            "location": {
                "latitude": 1.2830,
                "longitude": 103.8442
            }
        },
        {
            "name": "Marina Bay Sands (End)",
            "location": {
                "latitude": 1.2834,
                "longitude": 103.8607
            }
        }
    ]

    logger.info("=" * 80)
    logger.info("TESTING ROUTE OPTIMIZATION FOR SINGAPORE ATTRACTIONS")
    logger.info("=" * 80)
    logger.info(f"\nOriginal order:")
    for i, place in enumerate(places):
        logger.info(f"  {i+1}. {place['name']}")

    # Test with DRIVE mode
    logger.info("\n--- Testing with DRIVE mode ---")
    result = get_optimized_daily_route(places, travel_mode="DRIVE")

    if result:
        logger.info(f"\n✓ Optimization successful!")
        logger.info(f"  Total distance: {result['total_distance_km']} km")
        logger.info(f"  Total duration: {result['total_duration_minutes']} minutes")
        logger.info(f"\nOptimized order:")
        for i, place in enumerate(result['optimized_places']):
            logger.info(f"  {i+1}. {place['name']}")

        # Calculate savings
        logger.info(f"\nOptimization indices: {result['optimized_order']}")

        return result
    else:
        logger.error("✗ Optimization failed")
        return None


def test_simple_waypoint_optimization():
    """
    Test basic waypoint optimization with 3 stops.
    """
    logger.info("\n" + "=" * 80)
    logger.info("TESTING SIMPLE 3-WAYPOINT OPTIMIZATION")
    logger.info("=" * 80)

    origin = {"latitude": 1.290270, "longitude": 103.851959}  # Raffles Place
    destination = {"latitude": 1.290270, "longitude": 103.851959}  # Back to Raffles Place

    # Deliberately unordered waypoints
    intermediates = [
        {"latitude": 1.279530, "longitude": 103.845138},  # Chinatown (furthest)
        {"latitude": 1.280095, "longitude": 103.863426},  # Marina Bay (east)
        {"latitude": 1.304280, "longitude": 103.833160}   # Orchard Road (northwest)
    ]

    waypoint_names = ["Chinatown", "Marina Bay", "Orchard Road"]

    logger.info(f"\nOriginal waypoint order: {' -> '.join(waypoint_names)}")

    result = compute_optimized_route(
        origin=origin,
        destination=destination,
        intermediates=intermediates,
        travel_mode="DRIVE"
    )

    if result:
        logger.info(f"\n✓ Optimization successful!")
        logger.info(f"  Total distance: {result['total_distance_km']} km")
        logger.info(f"  Total duration: {result['total_duration_minutes']} minutes")

        # Show optimized order
        optimized_names = [waypoint_names[i] for i in result['optimized_waypoint_order']]
        logger.info(f"  Optimized waypoint order: {' -> '.join(optimized_names)}")
        logger.info(f"  Index mapping: {result['optimized_waypoint_order']}")

        return result
    else:
        logger.error("✗ Optimization failed")
        return None


if __name__ == "__main__":
    logger.info("Starting Route Optimization Tests\n")

    # Test 1: Simple 3-waypoint optimization
    test_simple_waypoint_optimization()

    # Test 2: Full day Singapore attractions tour
    test_singapore_attractions_optimization()

    logger.info("\n" + "=" * 80)
    logger.info("TESTS COMPLETE")
    logger.info("=" * 80)
