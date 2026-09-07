# GPS-Based Vehicle Tracking System - Backend

## Project Purpose
This repository contains the backend service for the GPS-based Vehicle Tracking System. The project provides real-time vehicle monitoring, authenticated access control, user assignment management, GPS ingestion via REST & MQTT, current location telemetry, and historical trajectory queries.

### Implemented Phases Summary
- **Phase 1**: FastAPI foundation, health monitoring, and CORS configuration.
- **Phase 2**: PostgreSQL database integration with SQLAlchemy 2.x, psycopg 3, and connection pooling.
- **Phase 3**: ORM models (`User`, `Route`, `Vehicle`, `GPSData`), schema relationships, foreign keys, unique constraints, and spatial index optimization.
- **Phase 4**: Idempotent seed script (`Route A`, `Route B`, `BUS-001`, `BUS-002`, `userA`, `userB`) with bcrypt password hashing and assignment consistency checks.
- **Phase 5**: JWT authentication framework (login, password verification, token generation, decoding, expiry, protected endpoints).
- **Phase 6**: User assignment endpoints (`/me/assignment`, `/routes`, `/vehicles`) with backend authorization rules.
- **Phase 7**: GPS telemetry schemas, service layer, and REST `POST /gps` endpoint.
- **Phase 8**: MQTT GPS ingestion subscriber (`paho-mqtt`), non-blocking FastAPI lifecycle integration, topic/payload validation, and GPS simulator script.
- **Phase 9**: User-facing location & history endpoints (`GET /me/vehicle/location`, `GET /me/vehicle/history`) with strict backend authorization.
- **Phase 17**: Final production polish, Docker Compose setup, security audit, and documentation.
- **Phases 20–29**: Production PostgreSQL runtime verification, seed reconciliation, end-to-end REST telemetry validation, assigned route coordinates API integration, and pre-submission audit.

---

## Technology Stack
- **Language**: Python 3.10+
- **Framework**: FastAPI
- **ASGI Server**: Uvicorn
- **Database**: PostgreSQL 15+
- **ORM / Toolkit**: SQLAlchemy 2.x
- **PostgreSQL Driver**: psycopg 3 (`psycopg[binary]`)
- **Authentication**: JWT (`PyJWT`)
- **Password Hashing**: bcrypt
- **MQTT Broker**: Eclipse Mosquitto (port 1883)
- **MQTT Client**: Paho MQTT (`paho-mqtt`)
- **Containerization**: Docker & Docker Compose
- **Testing**: pytest & HTTPX (FastAPI TestClient)

---

## Database Schema & Architecture

The database is built on PostgreSQL with strict relational integrity, foreign key cascading rules, and performance-optimized indexes.

```
+------------------+         +-------------------+
|      routes      |         |     vehicles      |
|------------------|         |-------------------|
| id (PK)          |<---+    | id (PK)           |<---+
| name             |    |    | vehicle_number    |    |
| start_location   |    |    | status            |    |
| end_location     |    |    | route_id (FK)-----+----+
| route_coordinates|    |    | created_at        |    |
| created_at       |    |    +-------------------+    |
+------------------+    |              ^              |
          ^             |              | 1            |
          |             |              |              |
          |             |              | N            |
          |       +-----+----+   +-----+-------------+|
          |       |  users   |   |     gps_data      ||
          |       |----------|   |-------------------||
          +-------+ route_id |   | id (PK)           ||
                  |vehicle_id+---+ vehicle_id (FK)---+|
                  | username |   | latitude          ||
                  | email    |   | longitude         ||
                  | pass_hash|   | timestamp         ||
                  +----------+   | speed             ||
                                 | created_at        ||
                                 +-------------------+|
```

### Concise Relationship Description
- **User -> assigned Route**: Many-to-one relationship (`users.route_id -> routes.id`). Each user is assigned to a specific scheduled route.
- **User -> assigned Vehicle**: Many-to-one relationship (`users.vehicle_id -> vehicles.id`). Each user is assigned to a specific vehicle for monitoring.
- **Vehicle -> GPS history**: One-to-many relationship (`gps_data.vehicle_id -> vehicles.id`). A vehicle accumulates a chronological history of telemetry fixes.

### Tables & Column Details

#### 1. `users`
Represents driver and operator accounts authenticated via JWT.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key, Autoincrement | Unique identifier |
| `username` | `VARCHAR(50)` | UNIQUE, NOT NULL, Indexed | Login username |
| `email` | `VARCHAR(100)` | UNIQUE, NOT NULL, Indexed | Contact email address |
| `password_hash`| `VARCHAR(255)` | NOT NULL | Salted bcrypt password hash |
| `route_id` | `INTEGER` | ForeignKey(`routes.id`, ondelete="SET NULL"), Indexed | Assigned route |
| `vehicle_id` | `INTEGER` | ForeignKey(`vehicles.id`, ondelete="SET NULL"), Indexed | Assigned vehicle |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, Server Default `now()` | Record creation time |

#### 2. `routes`
Represents predefined travel paths and waypoints.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key, Autoincrement | Unique identifier |
| `name` | `VARCHAR(100)` | NOT NULL, Indexed | Route display title (e.g., "Route A") |
| `description` | `TEXT` | Nullable | Detailed route description |
| `start_location`| `VARCHAR(255)` | NOT NULL | Departure terminal |
| `end_location` | `VARCHAR(255)` | NOT NULL | Arrival destination |
| `route_coordinates`| `TEXT` | Nullable | GeoJSON/JSON array of route waypoint coordinates |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, Server Default `now()` | Record creation time |

#### 3. `vehicles`
Represents transport units tracked across the fleet.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key, Autoincrement | Unique identifier |
| `vehicle_number`| `VARCHAR(50)` | UNIQUE, NOT NULL, Indexed | Fleet registration / badge (e.g., "BUS-001") |
| `status` | `VARCHAR(30)` | NOT NULL, Default `'active'` | Operational status (`active`, `maintenance`, `inactive`) |
| `route_id` | `INTEGER` | ForeignKey(`routes.id`, ondelete="SET NULL"), Indexed | Assigned route |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, Server Default `now()` | Record creation time |

#### 4. `gps_data`
High-volume telemetry data recording geospatial fixes from vehicles.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | Primary Key, Autoincrement | Unique identifier |
| `vehicle_id` | `INTEGER` | ForeignKey(`vehicles.id`, ondelete="CASCADE"), NOT NULL, Indexed | Tracked vehicle reference |
| `latitude` | `FLOAT` | NOT NULL | WGS84 latitude coordinate |
| `longitude` | `FLOAT` | NOT NULL | WGS84 longitude coordinate |
| `timestamp` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, Indexed | Fix timestamp reported by sensor |
| `speed` | `FLOAT` | Nullable, Default `0.0` | Speed in km/h |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, Server Default `now()` | Database ingestion timestamp |

**Key Indexes on `gps_data`**:
- Single-column B-tree index on `vehicle_id` for fast vehicle filtering.
- Single-column B-tree index on `timestamp` for time-window queries.
- Composite index **`ix_gps_data_vehicle_timestamp`** on `(vehicle_id, timestamp)` specifically optimizing `GET /me/vehicle/location` (latest fix) and `GET /me/vehicle/history` (chronological telemetry order) without sequential table scans.

---

## Concise API Reference Table

| Method | Endpoint | Auth Required | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | No | Application heartbeat check |
| `GET` | `/health/db` | No | Database connection health check |
| `POST` | `/auth/login` | No | User login (returns JWT Bearer token) |
| `GET` | `/auth/me` | Bearer Token | Authenticated user profile |
| `GET` | `/me/assignment` | Bearer Token | Authenticated user's assigned route & vehicle |
| `GET` | `/routes/{route_id}` | Bearer Token | Detailed route info (authorized user only) |
| `GET` | `/vehicles/{vehicle_id}` | Bearer Token | Detailed vehicle info (authorized user only) |
| `POST` | `/gps` | Bearer Token | Ingest GPS telemetry fix via REST API |
| `GET` | `/me/vehicle/location` | Bearer Token | Latest GPS fix for user's assigned vehicle |
| `GET` | `/me/vehicle/history` | Bearer Token | Historical GPS fixes for user's assigned vehicle |

---

## GPS Telemetry Ingestion: MQTT & REST

The backend supports dual ingestion mechanisms:

1. **MQTT Telemetry (Preferred Production Transport)**:
   - Optimized for lightweight, event-driven streaming from edge GPS trackers or IoT gateways.
   - **Topic Pattern**: `vehicles/{vehicle_id}/gps` (e.g., `vehicles/1/gps`). Wildcard subscription: `vehicles/+/gps`.
   - **Lifespan Integration**: A non-blocking Paho MQTT background listener starts during FastAPI application startup.
   - **Fault Tolerant**: If the MQTT broker is unreachable or fails to connect, the background listener logs a warning without raising an unhandled exception. FastAPI startup proceeds normally.

2. **HTTP REST Ingestion (Supported & Sufficient for Local/Demo Operation)**:
   - Endpoint: `POST /gps` (authenticated with Bearer JWT).
   - Validates driver assignment to prevent unauthorized telemetry submission.
   - Sufficient for testing, demo operations, mobile clients, and environments where an MQTT broker is not running.
   - **Mosquitto is completely optional for REST-based testing.**

### Telemetry Payload Format
```json
{
  "vehicle_id": 1,
  "latitude": 12.9780,
  "longitude": 77.6000,
  "speed": 42.5,
  "timestamp": "2026-09-07T10:30:00Z"
}
```

---

## Running with Docker Compose (Recommended)

The provided `docker-compose.yml` orchestrates the complete production stack with three interconnected services:

```bash
docker compose up -d --build
```

### Services Included in Docker Compose
- **`api`**: The FastAPI backend application running on `http://localhost:8000`. Connected to Postgres and Mosquitto via internal Docker networking.
- **`postgres`**: Official PostgreSQL 15 container running on port `5432` with a persistent volume (`postgres_data`) and integrated health checks.
- **`mosquitto`**: Eclipse Mosquitto 2.0 MQTT broker container running on port `1883` with a persistent volume (`mosquitto_data`).

To stop all services:
```bash
docker compose down
```

---

## Running Locally Without Docker

### 1. Prerequisites
- Python 3.10+
- Running PostgreSQL 15+ database instance (configured database name: `vehicle_tracking`)
- *(Optional)* Eclipse Mosquitto MQTT broker (`localhost:1883`) — optional if testing via REST.

### 2. Environment Configuration
Create a `.env` file in the project root from `.env.example`:
```env
DATABASE_URL=postgresql+psycopg://<username>:<password>@localhost:5432/vehicle_tracking
SECRET_KEY=<random-32-byte-secret-key>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_TOPIC=vehicles/+/gps
```
*(Note: Never commit your `.env` file to version control. It is excluded by `.gitignore`.)*

### 3. Setup Virtual Environment & Install Dependencies
```bash
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Database Setup & Seed
```bash
python -m app.db.init_db
python -m app.db.seed
```

### 5. Start Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
FastAPI documentation will be accessible at `http://localhost:8000/docs`.

---

## Development Seed Credentials

| Role / User | Username | Password | Assigned Route | Assigned Vehicle |
| :--- | :--- | :--- | :--- | :--- |
| Driver / User A | `userA` | `password123` | Route A (`#1`) | BUS-001 (`#1`) |
| Driver / User B | `userB` | `password123` | Route B (`#2`) | BUS-002 (`#2`) |

*Note: These credentials are used strictly for local development, automated testing, and evaluation.*

---

## Running the GPS Simulator

To stream simulated GPS telemetry over MQTT (when Mosquitto is active):
```bash
python scripts/gps_simulator.py --vehicle-id 1 --interval 2.0
```

---

## Running Backend Tests

Run the complete regression test suite:
```bash
pytest -v --tb=short
```
Expected result: **131 passed**.
