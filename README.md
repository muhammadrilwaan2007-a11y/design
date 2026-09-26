# SafeRoute AI 🗺️🛡️

[![React](https://img.shields.io/badge/React-18-blue.svg)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-CSS-38B2AC.svg)](https://tailwindcss.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**SafeRoute AI** is an intelligent navigation system designed for high-density, chaotic urban traffic environments (primarily built for Bengaluru). 

While traditional navigation apps focus strictly on the *fastest* route, SafeRoute AI goes a step further by evaluating the **safest** route. It aggregates live traffic, active incidents, hyper-local weather, and historical accident hotspots to predict route risk and steer drivers away from danger.

---

## 🌟 Core Features & Modules

SafeRoute AI is built modularly. Here is the current progress of the core system:

- ✅ **Module 1: Location & Search** — Geocoding and reverse geocoding via TomTom Search API.
- ✅ **Module 2: Traffic-Aware Routing** — Core routing engine powered by the TomTom Routing API, generating real-time ETAs that actively detour around jams and closed roads.
- ✅ **Module 3: Live Traffic Flow** — Overlay of real-time traffic congestion metrics on generated routes.
- ✅ **Module 4: Live Incidents** — Detection of live accidents, roadworks, and hazards within a 150m radius of the route.
- ✅ **Module 5: Weather Integration** — Integration with OpenWeather to assess weather risks (heavy rain, reduced visibility) along the journey.
- ✅ **Module 6: Historical Accident Analysis** — A backend ETL pipeline using `GeoPandas` and `DBSCAN` clustering to extract dangerous "accident hotspots" from noisy historical police crash data in Bengaluru.
- ⏳ **Module 7: Spatial Feature Engineering** *(In Progress)* — Calculating spatial intersections between candidate routes and historical hotspots/infrastructure.
- ⏳ **Module 8: ML Safety Risk Engine** *(Planned)* — The final machine learning model that will generate a 0-100 "Safety Score" for each route based on data from Modules 1-7.

---

## 🏗️ Architecture & Tech Stack

The project is structured as a decoupled monorepo.

### Frontend
- **Framework:** React + Vite
- **Styling:** Tailwind CSS + Lucide React Icons
- **Mapping:** React-Leaflet (OpenStreetMap Tiles)
- **State Management:** Custom React Hooks (`useRoute`, `useTraffic`, `useIncidents`)

### Backend
- **Framework:** FastAPI (Python)
- **Data Processing:** Pandas, GeoPandas, Scikit-learn (DBSCAN), Shapely
- **HTTP Client:** HTTPX (Async API calls)
- **Validation:** Pydantic (Strict typing for GeoJSON schemas)

### External APIs
- **TomTom**: Routing API, Search API, Traffic Flow API, Incident API.
- **OpenWeather**: Current weather metrics.

---

## 🚀 Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing.

### Prerequisites
- **Node.js** (v18+ recommended)
- **Python** (v3.10+ recommended)
- A **TomTom Developer Account** (for routing and traffic APIs)
- An **OpenWeather Account** (for weather APIs)

### 1. Clone & Configure Environment

Clone the repository and create the unified `.env` file at the root of the project (`saferoute_AI/.env`).

```env
# Backend Keys
TOMTOM_API_KEY=your_tomtom_api_key_here
OPENWEATHER_API_KEY=your_openweather_api_key_here

# Frontend Keys
VITE_TOMTOM_API_KEY=your_tomtom_api_key_here
VITE_API_BASE_URL=http://localhost:8000
```

### 2. Start the Backend (FastAPI)

Open a terminal and navigate to the backend directory to install dependencies and start the server:

```bash
cd backend
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server with hot-reload
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
*The backend API will be available at `http://127.0.0.1:8000`.*
*Interactive API documentation is automatically generated at `http://127.0.0.1:8000/docs`.*

### 3. Start the Frontend (React + Vite)

Open a **new** terminal window, navigate to the frontend directory, and start the Vite development server:

```bash
cd frontend
npm install
npm run dev
```
*The frontend application will be available at `http://localhost:5173`.*

---

## 📂 Project Structure

```text
saferoute_AI/
├── .env                  # Unified environment variables
├── .gitignore            # Unified git ignore rules
├── README.md             # Project documentation (You are here)
│
├── backend/              # Python FastAPI Application
│   ├── app/
│   │   ├── api/          # Route handlers (routing, weather, incidents)
│   │   ├── config/       # Pydantic settings loading from ../.env
│   │   ├── features/     # Module 6 ETL and clustering logic
│   │   ├── schemas/      # Pydantic data models & GeoJSON definitions
│   │   └── services/     # External API communication (TomTom, OpenWeather)
│   ├── data/             # Processed historical accident GeoJSONs
│   ├── main.py           # FastAPI entry point
│   └── requirements.txt  
│
└── frontend/             # React + Vite Application
    ├── src/
    │   ├── components/   # UI Components (Map, RouteCards, SearchBar)
    │   ├── hooks/        # State management (useRoute, useWeather)
    │   ├── pages/        # Main views (HomePage, MapPage)
    │   └── services/     # Fetch wrappers routing to FastAPI backend
    ├── index.html
    ├── package.json
    ├── tailwind.config.js
    └── vite.config.js    # Configured to pull env vars from ../.env
```

---

## 🔮 Roadmap
- [ ] Connect Module 6 Hotspots to the frontend map for visual awareness.
- [ ] Implement Module 7 (Feature Engineering pipeline).
- [ ] Train and deploy the Module 8 (Safety Score XGBoost model).
- [ ] Transition map style to dynamic dark mode based on time of day.
