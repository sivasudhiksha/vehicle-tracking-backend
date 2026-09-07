from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.init_db import init_db
from app.models import GPSData, Route, User, Vehicle
from app.models.gps_data import GPSData as GPSDataDirect
from app.models.route import Route as RouteDirect
from app.models.user import User as UserDirect
from app.models.vehicle import Vehicle as VehicleDirect


def test_models_can_be_imported():
    """1. Verify all four models can be imported cleanly."""
    assert User is not None
    assert Route is not None
    assert Vehicle is not None
    assert GPSData is not None
    assert User is UserDirect
    assert Route is RouteDirect
    assert Vehicle is VehicleDirect
    assert GPSData is GPSDataDirect


def test_models_registered_in_base_metadata():
    """2. Verify all four models are registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {"users", "routes", "vehicles", "gps_data"}
    assert expected_tables.issubset(table_names), (
        f"Missing tables in Base.metadata. Found: {table_names}"
    )


def test_table_names_are_correct():
    """3. Verify table names for all four models."""
    assert User.__tablename__ == "users"
    assert Route.__tablename__ == "routes"
    assert Vehicle.__tablename__ == "vehicles"
    assert GPSData.__tablename__ == "gps_data"


def test_user_route_relationship():
    """4. Verify User <-> Route relationship exists and is bidirectional."""
    user_mapper = inspect(User)
    route_mapper = inspect(Route)

    assert "route" in user_mapper.relationships
    assert user_mapper.relationships["route"].entity.class_ is Route
    assert user_mapper.relationships["route"].back_populates == "users"

    assert "users" in route_mapper.relationships
    assert route_mapper.relationships["users"].entity.class_ is User
    assert route_mapper.relationships["users"].back_populates == "route"


def test_user_vehicle_relationship():
    """5. Verify User <-> Vehicle relationship exists and is bidirectional."""
    user_mapper = inspect(User)
    vehicle_mapper = inspect(Vehicle)

    assert "vehicle" in user_mapper.relationships
    assert user_mapper.relationships["vehicle"].entity.class_ is Vehicle
    assert user_mapper.relationships["vehicle"].back_populates == "users"

    assert "users" in vehicle_mapper.relationships
    assert vehicle_mapper.relationships["users"].entity.class_ is User
    assert vehicle_mapper.relationships["users"].back_populates == "vehicle"


def test_vehicle_route_relationship():
    """6. Verify Vehicle <-> Route relationship exists and is bidirectional."""
    vehicle_mapper = inspect(Vehicle)
    route_mapper = inspect(Route)

    assert "route" in vehicle_mapper.relationships
    assert vehicle_mapper.relationships["route"].entity.class_ is Route
    assert vehicle_mapper.relationships["route"].back_populates == "vehicles"

    assert "vehicles" in route_mapper.relationships
    assert route_mapper.relationships["vehicles"].entity.class_ is Vehicle
    assert route_mapper.relationships["vehicles"].back_populates == "route"


def test_vehicle_gps_data_relationship():
    """7. Verify Vehicle -> GPSData relationship exists."""
    vehicle_mapper = inspect(Vehicle)
    assert "gps_records" in vehicle_mapper.relationships
    assert vehicle_mapper.relationships["gps_records"].entity.class_ is GPSData
    assert vehicle_mapper.relationships["gps_records"].back_populates == "vehicle"


def test_gps_data_vehicle_relationship():
    """8. Verify GPSData -> Vehicle relationship exists."""
    gps_mapper = inspect(GPSData)
    assert "vehicle" in gps_mapper.relationships
    assert gps_mapper.relationships["vehicle"].entity.class_ is Vehicle
    assert gps_mapper.relationships["vehicle"].back_populates == "gps_records"


def test_unique_constraints():
    """9. Verify unique constraints exist for username, email, and vehicle_number."""
    users_table = Base.metadata.tables["users"]
    vehicles_table = Base.metadata.tables["vehicles"]

    # Check username is unique
    username_col = users_table.columns["username"]
    assert username_col.unique is True or any(
        username_col.name in idx.columns for idx in users_table.indexes if idx.unique
    )

    # Check email is unique
    email_col = users_table.columns["email"]
    assert email_col.unique is True or any(
        email_col.name in idx.columns for idx in users_table.indexes if idx.unique
    )

    # Check vehicle_number is unique
    veh_num_col = vehicles_table.columns["vehicle_number"]
    assert veh_num_col.unique is True or any(
        veh_num_col.name in idx.columns for idx in vehicles_table.indexes if idx.unique
    )


def test_gps_indexes():
    """10. Verify indexes exist for vehicle_id, timestamp, and composite (vehicle_id, timestamp)."""
    gps_table = Base.metadata.tables["gps_data"]

    # Check vehicle_id has an index
    assert gps_table.columns["vehicle_id"].index is True

    # Check timestamp has an index
    assert gps_table.columns["timestamp"].index is True

    # Check composite index on (vehicle_id, timestamp)
    composite_indexes = [
        idx for idx in gps_table.indexes
        if [col.name for col in idx.columns] == ["vehicle_id", "timestamp"]
    ]
    assert len(composite_indexes) > 0, (
        f"Composite index (vehicle_id, timestamp) not found in {gps_table.indexes}"
    )


def test_database_table_creation_and_orm_operations():
    """Functional test: creates all tables in memory and exercises model relationships."""
    test_engine = create_engine("sqlite:///:memory:")
    init_db(target_engine=test_engine)

    TestSession = sessionmaker(bind=test_engine)
    session: Session = TestSession()

    now = datetime.now(timezone.utc)

    # Create Route
    route = Route(
        name="Route 101 - Downtown Express",
        description="Daily downtown express route",
        start_location="Central Station",
        end_location="North Terminal",
        route_coordinates="[[12.9716, 77.5946], [12.9780, 77.6000]]",
    )
    session.add(route)
    session.commit()
    session.refresh(route)
    assert route.id is not None

    # Create Vehicle assigned to Route
    vehicle = Vehicle(
        vehicle_number="KA-01-AB-1234",
        status="active",
        route_id=route.id,
    )
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)
    assert vehicle.id is not None
    assert vehicle.route.name == "Route 101 - Downtown Express"

    # Create User assigned to Route and Vehicle
    user = User(
        username="driver_alex",
        email="alex@transport.example",
        password_hash="mock_hash_for_phase_3_testing",
        route_id=route.id,
        vehicle_id=vehicle.id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    assert user.id is not None
    assert user.route.id == route.id
    assert user.vehicle.id == vehicle.id

    # Create GPSData for Vehicle
    gps_data = GPSData(
        vehicle_id=vehicle.id,
        latitude=12.971598,
        longitude=77.594566,
        timestamp=now,
        speed=42.5,
    )
    session.add(gps_data)
    session.commit()
    session.refresh(gps_data)
    assert gps_data.id is not None
    assert gps_data.vehicle.vehicle_number == "KA-01-AB-1234"
    assert len(vehicle.gps_records) == 1

    session.close()
