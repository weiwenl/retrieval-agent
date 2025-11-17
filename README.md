# EcoNav SG - Intelligent Travel Retrieval & Transport Agent System

A **monorepo** containing two **independent** agents for Singapore travel planning. Each agent solves a distinct problem with different architectures and can be run standalone.

## Overview

This repository contains two specialized agents that operate **independently** with different input requirements:

### Research Agent
**Purpose**: Discovers attractions and food venues from user travel preferences
**Architecture**: LLM-powered ReAct reasoning with adaptive search strategies
**Input**: User requirements (interests, dates, budget, pace)
**Output**: Curated list of places with geographic diversity and carbon scores

### Transport Agent
**Purpose**: Calculates multi-modal transport routes between specific locations
**Architecture**: Deterministic algorithmic processing with rule-based filtering
**Input**: Pre-defined itinerary with place coordinates and timestamps
**Output**: Point-to-point transport options with carbon emissions and costs

**IMPORTANT**: These agents do **NOT** work sequentially. They are separate tools that:
- Accept completely different input formats
- Can be run independently without each other
- Serve different use cases (place discovery vs. route calculation)

### Key Features

- **Adaptive Place Discovery**: ReAct-based reasoning adjusts search strategies based on results
- **Geographic Diversity**: Ensures balanced coverage across Singapore's 7 geo-clusters
- **Multi-Modal Transport**: Compares walking, cycling, public transit, and ride-hailing options
- **Carbon-Aware Planning**: Calculates precise CO2 emissions using Singapore-specific factors
- **Deterministic Transport**: Rule-based filtering ensures consistent, reliable route calculations

### Use Cases

**Research Agent** (runs independently):
- Generate diverse attraction recommendations based on user interests
- Discover dining options distributed across Singapore's geographic regions
- Find places with balanced coverage across different areas
- Get carbon-aware venue suggestions

**Transport Agent** (runs independently):
- Calculate transport options between known locations
- Compare carbon footprints across different transport modes (walk/cycle/transit/ride)
- Get cost estimates for point-to-point journeys
- Analyze multi-modal route combinations for existing itineraries

## Architecture

This monorepo contains two **independent** agents that can be run separately:

```
┌───────────────────────────────────────────────────────────┐
│                         MONOREPO                          │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────────────┐        ┌─────────────────────┐   │
│  │   Research Agent    │        │  Transport Agent    │   │
│  │   (ReAct + LLM)     │        │  (Deterministic)    │   │
│  │                     │        │                     │   │
│  │ INPUT:              │        │ INPUT:              │   │
│  │ - User interests    │        │ - Itinerary with    │   │
│  │ - Travel dates      │        │   coordinates       │   │
│  │ - Budget/pace       │        │ - Timestamps        │   │
│  │                     │        │                     │   │
│  │ PROCESS:            │        │ PROCESS:            │   │
│  │ - Adaptive Search   │        │ - Route Calc        │   │
│  │ - Geo Clustering    │        │ - Mode Filtering    │   │
│  │ - Carbon Scoring    │        │ - Carbon Estimate   │   │
│  │                     │        │                     │   │
│  │ OUTPUT:             │        │ OUTPUT:             │   │
│  │ - Places list JSON  │        │ - Transport JSON    │   │
│  └─────────────────────┘        └─────────────────────┘   │
│                                                           │
│  Can run independently          Can run independently     │
│  Different input format         Different input format    │
└───────────────────────────────────────────────────────────┘
```

## Technology Stack

### Shared
- **Python 3.12** - Core programming language
- **python-dotenv** - Environment variable management

### Research Agent Only
- **OpenAI GPT-4o** - LLM for adaptive search reasoning
- **OpenAI Function Calling** - Tool orchestration
- **ReAct Pattern** - Adaptive reasoning loop (Thought-Action-Observation)
- **Google Places API v1** - Place discovery and details

### Transport Agent Only
- **Google Routes API v2** - Multi-modal route calculations
- **Deterministic Algorithms** - Rule-based filtering and processing

## Quick Start

### Prerequisites

- Python 3.12+
- pip (Python package manager)
- OpenAI API key
- Google Maps API key (with Places API and Routes API enabled)

### 1. Environment Setup

Create a `.env` file in the root directory:

```bash
# Create .env file
touch .env

# Edit .env and add your API keys:
OPENAI_API_KEY=sk-your-openai-api-key-here
GOOGLE_MAPS_API_KEY=your-google-maps-api-key-here
```

**Required API Keys:**
- **OPENAI_API_KEY**: Get from https://platform.openai.com/api-keys
- **GOOGLE_MAPS_API_KEY**: Get from https://console.cloud.google.com/apis/credentials
  - Enable: Places API (New), Routes API

### 2. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt
```

**Core Dependencies:**
- openai
- google-maps-services
- boto3 (for AWS deployment)
- python-dotenv
- requests

### 3. Running Locally

#### Research Agent

**Purpose**: Discover attractions and food venues based on user preferences

```bash
# Navigate to Research Agent directory
cd ResearchAgent

# Run with input file
python main.py inputs/20251102T194622_fe4gH412.json

# Or specify custom output file
python main.py inputs/20251102T194622_fe4gH412.json outputs/20251102T194622_fe4gH412.json
```

**Input Format** (`inputs/20251102T194622_fe4gH412.json`):
```json
{
  "destination_city": "Singapore",
  "trip_dates": {
      "start_date": "2026-11-01",
      "end_date": "2026-11-05"
  },
  "duration_days": 5,
  "travelers": {
      "adults": 2,
      "children": 0
  },
  "budget_total_sgd": 100,
  "pace": "moderate",
  "optional": {
      "eco_preferences": "no",
      "dietary_preferences": "indian",
      "interests": [
          "I want to go to the aquarium sea and zoo in singapore"
      ],
      "uninterests": [],
      "accessibility_needs": "no_preference",
      "accommodation_location": {
          "neighborhood": "near bugis"
      },
      "group_type": "family"
  }
}
```

**Output Format**: `outputs/20251102T194622_fe4gH412.json` with discovered places
```json
{
  "retrieval": {
    "places_matrix": {
      "candidates": [
        {
          "place_id": "ChIJ...",
          "name": "Gardens by the Bay",
          "geo": {"latitude": 1.2816, "longitude": 103.8636},
          "geo_cluster_id": "central",
          "onsite_co2_kg": 2.5,
          "low_carbon_score": 85,
          "tags": ["nature", "outdoor", "family-friendly"]
        }
      ]
    }
  }
}
```

#### Transport Agent

**Purpose**: Calculate transport options between itinerary destinations

```bash
# Navigate to Transport Agent directory
cd TransportAgent

# Run with input file from Planning Agent
python main.py inputs/20251106T112455_ro6765put.json

# Or specify custom output file
python main.py inputs/20251106T112455_ro6765put.json outputs/20251106T112455_ro6765put.json
```

**Input Format** (`inputs/20251106T112455_ro6765put.json`):
```json
{
  "requirements": {
    "optional": {
      "accommodation_location": {
        "neighborhood": "near the Jurong Mall",
        "lat": 1.3397443,
        "lng": 103.7067297,
        "place_id": "ChIJa9YM2-wP2jERmOUStQKyiS0",
        "name": "Jurong Point"
      },
    }
  },
  "itinerary": {
    "2025-06-01": {
      "morning": {
        "time": "10:00",
        "items": {
          "name": "Gardens by the Bay",
          "place_id": "ChIJ...",
          "geo": {"latitude": 1.2815683, "longitude": 103.8636132}
        }
      },
      "lunch": {
        "time": "12:00",
        "items": {
          "name": "Maxwell Food Centre",
          "place_id": "ChIJ...",
          "geo": {"latitude": 1.2803361, "longitude": 103.844767}
        }
      }
    }
  }
}
```

**Output Format**: `outputs/20251106T112455_ro6765put.json` with route calculations
```json
{
  "transport": {
    "2025-01-15": {
      "connections": [
        {
          "connection_id": 1,
          "from_place_name": "Accommodation",
          "to_place_name": "Gardens by the Bay",
          "transport_modes": [
            {
              "mode": "mrt",
              "distance_km": 5.2,
              "duration_minutes": 18,
              "cost_sgd": 1.54,
              "carbon_kg": 0.182,
              "transit_summary": "MRT Circle Line"
            }
          ]
        }
      ]
    }
  }
}
```

## Agent Details

### Research Agent

**Architecture**: ReAct (Reasoning + Acting) pattern with LLM-driven adaptive search

**Core Capabilities:**
- **Requirements Analysis**: Calculates place needs based on pace and duration
- **Adaptive Search**: Adjusts radius (10km → 20km → 30km → 35km) based on results
- **Geographic Diversity**: Ensures coverage across 7 Singapore geo-clusters
- **Quality Evaluation**: Scores diversity, relevance, and geographic spread
- **Carbon Scoring**: Assigns onsite emissions (0-100 scale) based on venue type

**Tools:**
- `map_interest_to_place_types` - Converts interests to Google Place types
- `search_places` - Queries Google Places API with adaptive parameters
- `evaluate_results_quality` - Assesses search quality metrics
- `get_place_details` - Fetch detailed information for specific places by place_id

**Fallback Strategies:**
- Progressive radius expansion (10km → 35km in 10km steps)
- Rating relaxation (4.0 → 3.0 for attractions, 4.5 → 3.5 for food)
- Food search with cluster-based distribution (5km → 15km → 25km → 35km per cluster)
- API retry with exponential backoff (0.5s → 1s → 2s)

### Transport Agent

**Architecture**: Deterministic algorithmic processing with hardcoded filtering rules

**Core Capabilities:**
- **Multi-Modal Calculation**: Parallel API calls for WALK, TRANSIT, DRIVE modes
- **Intelligent Filtering**: Removes impractical options based on thresholds
- **Carbon Estimation**: Singapore-specific emission factors (kg CO2/km)
- **Cost Calculation**: MRT ($0.92 + $0.12/km), Taxi ($3.90 + $0.55/km)

**Transport Modes:**
- Walking: ≤2km (converted to cycling if >2km)
- Cycling: 2-8km range, 15 km/h average speed
- Public Transit: MRT/bus with transfer details (max 3 transfers)
- Ride-hailing: Grab/taxi with cost estimates (always included as fallback)

**Filtering Rules:**
- Walking: >2km → convert to cycling
- Cycling: >8km → remove
- Public Transit: >3 transfers → remove
                  >60min duration → remove
                  >1.5km walking within transit → remove
- Ride-hailing: Always included (guaranteed fallback)

**Carbon Emission Factors (kg CO2/km):**
- Walking: 0.00
- Cycling: 0.00
- MRT: 0.035
- Bus: 0.09
- Taxi: 0.22

## Project Structure

```
retrieval-agent/
├── ResearchAgent/
│   ├── main.py              # ReAct agent with adaptive search
│   ├── tools.py             # Google Places API tools
│   ├── config.py            # Configuration and constants
│   ├── inputs/              # Sample input files
│   └── outputs/             # Generated outputs
│
├── TransportAgent/
│   ├── main.py              # Deterministic route processor
│   ├── tools.py             # Google Routes API tools
│   ├── config.py            # Transport thresholds
│   ├── singapore_transport_carbon_score.py  # Emission factors
│   ├── inputs/              # Sample itineraries
│   └── outputs/             # Route calculations
│
├── .env                     # API keys (create this)
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

<div align="center">

**Built with ❤️ by [Lee Wei Wen/Architecting AI Systems - NUS]**

</div>
