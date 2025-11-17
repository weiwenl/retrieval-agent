"""
Unit tests for TransportAgent itinerary processing logic.

Tests verify that the calculate_day_by_day_routes function correctly handles:
- Multiple date keys in itinerary
- Dynamic time periods (not hardcoded to morning/lunch/afternoon)
- Both single object and array of objects in "items"
- Null/empty items
- Sorting by time
- Accommodation as starting point
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'TransportAgent'))

import unittest
from unittest.mock import Mock, patch
from main import TransportSustainabilityAgent


class TestTransportItineraryProcessing(unittest.TestCase):
    """Test suite for transport agent itinerary processing logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.agent = TransportSustainabilityAgent()
        self.accommodation = {
            "lat": 1.3397443,
            "lng": 103.7067297
        }

        # Mock transport response
        self.mock_transport_response = {
            "DRIVE": {
                "distance_km": 5.0,
                "duration_minutes": 10,
                "estimated_cost_sgd": 8.0
            }
        }

    @patch('tools.get_transport_options_concurrent')
    def test_items_as_array(self, mock_transport):
        """Test processing when items is an array of places."""
        mock_transport.return_value = self.mock_transport_response

        places_data = {
            "itinerary": {
                "2025-06-01": {
                    "morning": {
                        "time": "10:00",
                        "items": [
                            {
                                "place_id": "place1",
                                "name": "Place 1",
                                "geo": {"latitude": 1.28, "longitude": 103.85}
                            },
                            {
                                "place_id": "place2",
                                "name": "Place 2",
                                "geo": {"latitude": 1.29, "longitude": 103.86}
                            }
                        ]
                    }
                }
            },
            "requirements": {}
        }

        result = self.agent.calculate_day_by_day_routes(places_data, self.accommodation)

        # Should create 2 connections: accommodation->place1, place1->place2
        self.assertIn("2025-06-01", result)
        connections = result["2025-06-01"]["connections"]
        self.assertEqual(len(connections), 2)
        self.assertEqual(connections[0]["from_place_name"], "Accommodation")
        self.assertEqual(connections[0]["to_place_name"], "Place 1")
        self.assertEqual(connections[1]["from_place_name"], "Place 1")
        self.assertEqual(connections[1]["to_place_name"], "Place 2")

    @patch('tools.get_transport_options_concurrent')
    def test_items_as_single_object(self, mock_transport):
        """Test processing when items is a single object (not array)."""
        mock_transport.return_value = self.mock_transport_response

        places_data = {
            "itinerary": {
                "2025-06-01": {
                    "morning": {
                        "time": "10:00",
                        "items": {
                            "place_id": "place1",
                            "name": "Single Place",
                            "geo": {"latitude": 1.28, "longitude": 103.85}
                        }
                    }
                }
            },
            "requirements": {}
        }

        result = self.agent.calculate_day_by_day_routes(places_data, self.accommodation)

        # Should create 1 connection: accommodation->place1
        connections = result["2025-06-01"]["connections"]
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0]["to_place_name"], "Single Place")

    @patch('tools.get_transport_options_concurrent')
    def test_null_and_empty_items(self, mock_transport):
        """Test that null items and empty arrays are skipped."""
        mock_transport.return_value = self.mock_transport_response

        places_data = {
            "itinerary": {
                "2025-06-01": {
                    "morning": {
                        "time": "10:00",
                        "items": None  # Null items
                    },
                    "lunch": {
                        "time": "12:00",
                        "items": []  # Empty array
                    },
                    "afternoon": {
                        "time": "15:00",
                        "items": [
                            {
                                "place_id": "place1",
                                "name": "Valid Place",
                                "geo": {"latitude": 1.28, "longitude": 103.85}
                            }
                        ]
                    }
                }
            },
            "requirements": {}
        }

        result = self.agent.calculate_day_by_day_routes(places_data, self.accommodation)

        # Should only create 1 connection: accommodation->valid place (skipping null and empty)
        connections = result["2025-06-01"]["connections"]
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0]["to_place_name"], "Valid Place")

    @patch('tools.get_transport_options_concurrent')
    def test_dynamic_time_periods(self, mock_transport):
        """Test that time periods are not hardcoded (can be breakfast, dinner, etc.)."""
        mock_transport.return_value = self.mock_transport_response

        places_data = {
            "itinerary": {
                "2025-06-01": {
                    "breakfast": {  # Custom period name
                        "time": "08:00",
                        "items": [{"place_id": "p1", "name": "Breakfast Spot",
                                  "geo": {"latitude": 1.28, "longitude": 103.85}}]
                    },
                    "dinner": {  # Another custom period name
                        "time": "19:00",
                        "items": [{"place_id": "p2", "name": "Dinner Spot",
                                  "geo": {"latitude": 1.29, "longitude": 103.86}}]
                    }
                }
            },
            "requirements": {}
        }

        result = self.agent.calculate_day_by_day_routes(places_data, self.accommodation)

        # Should process both custom time periods
        connections = result["2025-06-01"]["connections"]
        self.assertEqual(len(connections), 2)
        self.assertEqual(connections[0]["to_place_name"], "Breakfast Spot")
        self.assertEqual(connections[1]["to_place_name"], "Dinner Spot")

    @patch('tools.get_transport_options_concurrent')
    def test_time_sorting(self, mock_transport):
        """Test that time periods are sorted chronologically."""
        mock_transport.return_value = self.mock_transport_response

        places_data = {
            "itinerary": {
                "2025-06-01": {
                    "afternoon": {  # Out of order
                        "time": "15:00",
                        "items": [{"place_id": "p3", "name": "Afternoon Place",
                                  "geo": {"latitude": 1.30, "longitude": 103.87}}]
                    },
                    "morning": {  # Should come first
                        "time": "10:00",
                        "items": [{"place_id": "p1", "name": "Morning Place",
                                  "geo": {"latitude": 1.28, "longitude": 103.85}}]
                    },
                    "lunch": {  # Should be middle
                        "time": "12:00",
                        "items": [{"place_id": "p2", "name": "Lunch Place",
                                  "geo": {"latitude": 1.29, "longitude": 103.86}}]
                    }
                }
            },
            "requirements": {}
        }

        result = self.agent.calculate_day_by_day_routes(places_data, self.accommodation)

        # Verify order: accommodation->morning->lunch->afternoon
        connections = result["2025-06-01"]["connections"]
        self.assertEqual(len(connections), 3)
        self.assertEqual(connections[0]["to_place_name"], "Morning Place")
        self.assertEqual(connections[1]["to_place_name"], "Lunch Place")
        self.assertEqual(connections[2]["to_place_name"], "Afternoon Place")

    @patch('tools.get_transport_options_concurrent')
    def test_multiple_dates(self, mock_transport):
        """Test processing multiple dates in itinerary."""
        mock_transport.return_value = self.mock_transport_response

        places_data = {
            "itinerary": {
                "2025-06-01": {
                    "morning": {
                        "time": "10:00",
                        "items": [{"place_id": "p1", "name": "Day 1 Place",
                                  "geo": {"latitude": 1.28, "longitude": 103.85}}]
                    }
                },
                "2025-06-02": {
                    "morning": {
                        "time": "10:00",
                        "items": [{"place_id": "p2", "name": "Day 2 Place",
                                  "geo": {"latitude": 1.29, "longitude": 103.86}}]
                    }
                }
            },
            "requirements": {}
        }

        result = self.agent.calculate_day_by_day_routes(places_data, self.accommodation)

        # Should have connections for both dates
        self.assertIn("2025-06-01", result)
        self.assertIn("2025-06-02", result)
        self.assertEqual(len(result["2025-06-01"]["connections"]), 1)
        self.assertEqual(len(result["2025-06-02"]["connections"]), 1)

    @patch('tools.get_transport_options_concurrent')
    def test_accommodation_always_first(self, mock_transport):
        """Test that accommodation is always the starting point."""
        mock_transport.return_value = self.mock_transport_response

        places_data = {
            "itinerary": {
                "2025-06-01": {
                    "morning": {
                        "time": "10:00",
                        "items": [{"place_id": "p1", "name": "First Place",
                                  "geo": {"latitude": 1.28, "longitude": 103.85}}]
                    }
                }
            },
            "requirements": {}
        }

        result = self.agent.calculate_day_by_day_routes(places_data, self.accommodation)

        # First connection should start from accommodation
        connections = result["2025-06-01"]["connections"]
        self.assertEqual(connections[0]["from_place_id"], "accommodation")
        self.assertEqual(connections[0]["from_place_name"], "Accommodation")


if __name__ == '__main__':
    unittest.main()
