import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import verify_password
from app.db.seed import seed_database
from app.models import Route, User, Vehicle


@pytest.fixture
def test_db_engine():
    """Provides a clean in-memory SQLite database engine for each test."""
    test_engine = create_engine("sqlite:///:memory:")
    return test_engine


@pytest.fixture
def seeded_session(test_db_engine):
    """Seeds the in-memory database and provides an active session for verification."""
    seed_database(target_engine=test_db_engine)
    TestSession = sessionmaker(bind=test_db_engine)
    session: Session = TestSession()
    yield session
    session.close()


def test_seed_creates_routes(seeded_session: Session):
    """1. Verify seed creates Route A and Route B."""
    routes = seeded_session.scalars(select(Route)).all()
    route_names = {r.name for r in routes}
    assert "Route A" in route_names
    assert "Route B" in route_names
    assert len(routes) == 2


def test_seed_creates_vehicles(seeded_session: Session):
    """2. Verify seed creates BUS-001 and BUS-002."""
    vehicles = seeded_session.scalars(select(Vehicle)).all()
    vehicle_numbers = {v.vehicle_number for v in vehicles}
    assert "BUS-001" in vehicle_numbers
    assert "BUS-002" in vehicle_numbers
    assert len(vehicles) == 2


def test_seed_creates_users(seeded_session: Session):
    """3. Verify seed creates userA and userB."""
    users = seeded_session.scalars(select(User)).all()
    usernames = {u.username for u in users}
    assert "userA" in usernames
    assert "userB" in usernames
    assert len(users) == 2


def test_passwords_stored_as_hashes_not_plaintext(seeded_session: Session):
    """4. Verify passwords are stored as secure bcrypt hashes, never plaintext."""
    user_a = seeded_session.scalars(select(User).where(User.username == "userA")).first()
    user_b = seeded_session.scalars(select(User).where(User.username == "userB")).first()

    assert user_a is not None
    assert user_b is not None

    # Ensure passwords are not stored in plaintext
    assert user_a.password_hash != "password123"
    assert user_b.password_hash != "password123"

    # Ensure hashes follow standard bcrypt format
    assert user_a.password_hash.startswith("$2b$")
    assert user_b.password_hash.startswith("$2b$")

    # Ensure the hashes can be verified against the plaintext password
    assert verify_password("password123", user_a.password_hash) is True
    assert verify_password("password123", user_b.password_hash) is True
    assert verify_password("wrongpassword", user_a.password_hash) is False


def test_usera_assigned_route_a(seeded_session: Session):
    """5. Verify userA is assigned to Route A."""
    user_a = seeded_session.scalars(select(User).where(User.username == "userA")).first()
    route_a = seeded_session.scalars(select(Route).where(Route.name == "Route A")).first()

    assert user_a is not None
    assert route_a is not None
    assert user_a.route_id == route_a.id
    assert user_a.route.name == "Route A"


def test_usera_assigned_bus_001(seeded_session: Session):
    """6. Verify userA is assigned to BUS-001."""
    user_a = seeded_session.scalars(select(User).where(User.username == "userA")).first()
    bus_001 = seeded_session.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first()

    assert user_a is not None
    assert bus_001 is not None
    assert user_a.vehicle_id == bus_001.id
    assert user_a.vehicle.vehicle_number == "BUS-001"


def test_userb_assigned_route_b(seeded_session: Session):
    """7. Verify userB is assigned to Route B."""
    user_b = seeded_session.scalars(select(User).where(User.username == "userB")).first()
    route_b = seeded_session.scalars(select(Route).where(Route.name == "Route B")).first()

    assert user_b is not None
    assert route_b is not None
    assert user_b.route_id == route_b.id
    assert user_b.route.name == "Route B"


def test_userb_assigned_bus_002(seeded_session: Session):
    """8. Verify userB is assigned to BUS-002."""
    user_b = seeded_session.scalars(select(User).where(User.username == "userB")).first()
    bus_002 = seeded_session.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-002")).first()

    assert user_b is not None
    assert bus_002 is not None
    assert user_b.vehicle_id == bus_002.id
    assert user_b.vehicle.vehicle_number == "BUS-002"


def test_bus_001_belongs_to_route_a(seeded_session: Session):
    """9. Verify BUS-001 belongs to Route A."""
    bus_001 = seeded_session.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first()
    route_a = seeded_session.scalars(select(Route).where(Route.name == "Route A")).first()

    assert bus_001 is not None
    assert route_a is not None
    assert bus_001.route_id == route_a.id
    assert bus_001.route.name == "Route A"


def test_bus_002_belongs_to_route_b(seeded_session: Session):
    """10. Verify BUS-002 belongs to Route B."""
    bus_002 = seeded_session.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-002")).first()
    route_b = seeded_session.scalars(select(Route).where(Route.name == "Route B")).first()

    assert bus_002 is not None
    assert route_b is not None
    assert bus_002.route_id == route_b.id
    assert bus_002.route.name == "Route B"


def test_running_seed_twice_does_not_create_duplicates(test_db_engine):
    """11. Verify seed idempotency: running twice produces zero new records and no duplicates."""
    first_run = seed_database(target_engine=test_db_engine)
    assert first_run == {
        "routes_created": 2,
        "vehicles_created": 2,
        "users_created": 2,
    }

    second_run = seed_database(target_engine=test_db_engine)
    assert second_run == {
        "routes_created": 0,
        "vehicles_created": 0,
        "users_created": 0,
    }

    TestSession = sessionmaker(bind=test_db_engine)
    with TestSession() as session:
        routes_count = len(session.scalars(select(Route)).all())
        vehicles_count = len(session.scalars(select(Vehicle)).all())
        users_count = len(session.scalars(select(User)).all())

        assert routes_count == 2
        assert vehicles_count == 2
        assert users_count == 2


def test_seed_preserves_assignment_consistency(test_db_engine):
    """12. Verify seed restores and enforces assignment consistency across runs."""
    seed_database(target_engine=test_db_engine)

    TestSession = sessionmaker(bind=test_db_engine)
    with TestSession() as session:
        user_a = session.scalars(select(User).where(User.username == "userA")).first()
        route_b = session.scalars(select(Route).where(Route.name == "Route B")).first()
        # Simulate accidental corrupt assignment
        user_a.route_id = route_b.id
        session.commit()

    # Re-running seed should correct inconsistencies
    seed_database(target_engine=test_db_engine)

    with TestSession() as session:
        user_a = session.scalars(select(User).where(User.username == "userA")).first()
        route_a = session.scalars(select(Route).where(Route.name == "Route A")).first()
        bus_001 = session.scalars(select(Vehicle).where(Vehicle.vehicle_number == "BUS-001")).first()

        assert user_a.route_id == route_a.id
        assert user_a.vehicle_id == bus_001.id
