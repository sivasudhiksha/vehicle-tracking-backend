"""MQTT message handler module.

Processes incoming MQTT messages, validates payload structure and vehicle ID consistency,
and delegates database storage to the existing GPS service layer.
"""

import json
import logging
import re
from typing import Any, Callable

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.gps_data import GPSData
from app.schemas.gps import GPSDataCreate
from app.services.gps_service import ingest_gps_record

logger = logging.getLogger("app.mqtt.handlers")

# Regex pattern to match topic: vehicles/{vehicle_id}/gps
TOPIC_VEHICLE_REGEX = re.compile(r"^vehicles/(\d+)/gps$")


def extract_vehicle_id_from_topic(topic: str) -> int | None:
    """Extract integer vehicle_id from topic formatted as vehicles/{vehicle_id}/gps.

    Returns:
        int | None: The extracted vehicle ID or None if topic does not match pattern.
    """
    match = TOPIC_VEHICLE_REGEX.match(topic)
    if match:
        return int(match.group(1))
    return None


def handle_mqtt_message(
    topic: str,
    payload_bytes: bytes | str,
    db_factory: Callable[[], Session] = SessionLocal,
) -> GPSData | None:
    """Parse, validate, and store a GPS record received via MQTT.

    Safe callback handler -- catches and logs all validation, format, and database errors
    without crashing the subscriber thread or application.

    Args:
        topic: The MQTT topic on which the message was received (e.g. 'vehicles/1/gps').
        payload_bytes: Raw binary or string MQTT message payload.
        db_factory: Callable returning an active SQLAlchemy Session (defaults to SessionLocal).

    Returns:
        GPSData | None: The persisted GPS record on success, or None on failure/rejection.
    """
    # 1. Parse JSON payload
    if isinstance(payload_bytes, bytes):
        try:
            raw_text = payload_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.warning("Rejected MQTT message: payload is not valid UTF-8 text. Error: %s", exc)
            return None
    else:
        raw_text = payload_bytes

    try:
        data: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("Rejected MQTT message: malformed JSON payload on topic '%s'. Error: %s", topic, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("Rejected MQTT message: payload JSON is not a dict on topic '%s'.", topic)
        return None

    # 2. Extract and check vehicle_id consistency between topic and payload
    topic_vehicle_id = extract_vehicle_id_from_topic(topic)
    payload_vehicle_id = data.get("vehicle_id")

    if topic_vehicle_id is not None and payload_vehicle_id is not None:
        try:
            if int(payload_vehicle_id) != topic_vehicle_id:
                logger.warning(
                    "Rejected MQTT message: topic vehicle_id (%d) does not match payload vehicle_id (%s).",
                    topic_vehicle_id,
                    payload_vehicle_id,
                )
                return None
        except (ValueError, TypeError):
            logger.warning("Rejected MQTT message: invalid payload vehicle_id '%s'.", payload_vehicle_id)
            return None

    # If payload is missing vehicle_id but topic has it, populate payload vehicle_id
    if payload_vehicle_id is None and topic_vehicle_id is not None:
        data["vehicle_id"] = topic_vehicle_id

    # 3. Validate using GPSDataCreate schema
    try:
        validated_payload = GPSDataCreate(**data)
    except (ValidationError, ValueError) as exc:
        logger.warning("Rejected MQTT message: validation failed on topic '%s'. Error: %s", topic, exc)
        return None

    # 4. Store using existing GPS service
    db = db_factory()
    try:
        record = ingest_gps_record(payload=validated_payload, db=db)
        logger.info("Successfully ingested MQTT GPS record for vehicle %d", record.vehicle_id)
        return record
    except ValueError as exc:
        logger.warning("Rejected MQTT message: vehicle lookup failed. Error: %s", exc)
        db.rollback()
        return None
    except Exception as exc:
        logger.error("Error storing MQTT GPS record in database: %s", exc)
        db.rollback()
        return None
    finally:
        db.close()