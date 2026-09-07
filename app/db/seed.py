import json
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.db.init_db import init_db
from app.db.session import SessionLocal, check_database_connection, engine
from app.models import Route, User, Vehicle

# Initial Seed Data Definitions
ROUTES_SEED = [
    {
        "name": "Route A",
        "description": "Main Route A",
        "start_location": "Location A Start",
        "end_location": "Location A End",
        "route_coordinates": json.dumps([
            [12.9716, 77.5946],
            [12.9780, 77.6000],
            [12.9850, 77.6050],
        ]),
    },
    {
        "name": "Route B",
        "description": "Main Route B",
        "start_location": "Location B Start",
        "end_location": "Location B End",
        "route_coordinates": json.dumps([
            [12.9250, 77.5800],
            [12.9300, 77.5850],
            [12.9350, 77.5900],
        ]),
    },
]

VEHICLES_SEED = [
    {
        "vehicle_number": "BUS-001",
        "status": "active",
        "route_name": "Route A",
    },
    {
        "vehicle_number": "BUS-002",
        "status": "active",
        "route_name": "Route B",
    },
]

USERS_SEED = [
    {
        "username": "userA",
        "email": "userA@example.com",
        "plain_password": "password123",
        "route_name": "Route A",
        "vehicle_number": "BUS-001",
    },
    {
        "username": "userB",
        "email": "userB@example.com",
        "plain_password": "password123",
        "route_name": "Route B",
        "vehicle_number": "BUS-002",
    },
]


def seed_database(
    session: Session | None = None,
    target_engine: Engine | None = None,
) -> dict[str, int]:
    """Idempotently seeds initial routes, vehicles, and users with consistent assignments.

    Args:
        session: Existing database session to use (e.g. for testing in an isolated transaction).
        target_engine: Optional SQLAlchemy Engine. If provided and session is None,
                       tables are ensured on this engine and a new session is opened.

    Returns:
        dict[str, int]: Count of new records created:
            {'routes_created': int, 'vehicles_created': int, 'users_created': int}
    """
    bind_engine = target_engine if target_engine is not None else engine
    init_db(target_engine=bind_engine)

    close_session_on_finish = False
    if session is None:
        if target_engine is not None:
            custom_maker = sessionmaker(autocommit=False, autoflush=False, bind=target_engine)
            db_session = custom_maker()
        else:
            db_session = SessionLocal()
        close_session_on_finish = True
    else:
        db_session = session

    routes_created = 0
    vehicles_created = 0
    users_created = 0

    try:
        with db_session.begin():
            # 1. Seed Routes
            routes_by_name: dict[str, Route] = {}
            for r_data in ROUTES_SEED:
                route = db_session.scalars(
                    select(Route).where(Route.name == r_data["name"])
                ).first()
                if not route:
                    route = Route(
                        name=r_data["name"],
                        description=r_data["description"],
                        start_location=r_data["start_location"],
                        end_location=r_data["end_location"],
                        route_coordinates=r_data["route_coordinates"],
                    )
                    db_session.add(route)
                    db_session.flush()
                    routes_created += 1
                routes_by_name[r_data["name"]] = route

            # 2. Seed Vehicles
            vehicles_by_number: dict[str, Vehicle] = {}
            for v_data in VEHICLES_SEED:
                vehicle = db_session.scalars(
                    select(Vehicle).where(Vehicle.vehicle_number == v_data["vehicle_number"])
                ).first()
                assigned_route = routes_by_name[v_data["route_name"]]
                if not vehicle:
                    vehicle = Vehicle(
                        vehicle_number=v_data["vehicle_number"],
                        status=v_data["status"],
                        route_id=assigned_route.id,
                    )
                    db_session.add(vehicle)
                    db_session.flush()
                    vehicles_created += 1
                else:
                    if vehicle.route_id != assigned_route.id:
                        vehicle.route_id = assigned_route.id
                vehicles_by_number[v_data["vehicle_number"]] = vehicle

            # 3. Seed Users
            for u_data in USERS_SEED:
                user = db_session.scalars(
                    select(User).where(User.username == u_data["username"])
                ).first()
                assigned_route = routes_by_name[u_data["route_name"]]
                assigned_vehicle = vehicles_by_number[u_data["vehicle_number"]]
                if not user:
                    user = User(
                        username=u_data["username"],
                        email=u_data["email"],
                        password_hash=get_password_hash(u_data["plain_password"]),
                        route_id=assigned_route.id,
                        vehicle_id=assigned_vehicle.id,
                    )
                    db_session.add(user)
                    db_session.flush()
                    users_created += 1
                else:
                    if user.route_id != assigned_route.id:
                        user.route_id = assigned_route.id
                    if user.vehicle_id != assigned_vehicle.id:
                        user.vehicle_id = assigned_vehicle.id
                    if not verify_password(u_data["plain_password"], user.password_hash):
                        user.password_hash = get_password_hash(u_data["plain_password"])

        return {
            "routes_created": routes_created,
            "vehicles_created": vehicles_created,
            "users_created": users_created,
        }
    except Exception:
        db_session.rollback()
        raise
    finally:
        if close_session_on_finish:
            db_session.close()


if __name__ == "__main__":
    is_connected, error = check_database_connection()
    if is_connected:
        print("Connected to PostgreSQL database. Seeding data...")
        result = seed_database()
        print(f"Seed completed: {result}")
    else:
        print(f"Notice: PostgreSQL connection unavailable ({error}).")
        print("Running seed on local development database (sqlite:///./dev_vehicle_tracking.db)...")
        dev_engine = create_engine("sqlite:///./dev_vehicle_tracking.db")
        result = seed_database(target_engine=dev_engine)
        print(f"Seed completed: {result}")
