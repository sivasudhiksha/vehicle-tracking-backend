"""MQTT subscriber client module for FastAPI lifecycle integration.

Manages the background Paho MQTT client lifecycle (connect, subscribe, reconnect, disconnect).
Guarantees non-blocking startup: connection failures are logged and do not crash the API server.
"""

import logging
import paho.mqtt.client as mqtt

from app.core.config import settings
from app.mqtt.handlers import handle_mqtt_message

logger = logging.getLogger("app.mqtt.client")

# Global client reference for lifecycle management
_mqtt_client: mqtt.Client | None = None


def create_mqtt_client() -> mqtt.Client:
    """Construct and configure the Paho MQTT client instance."""

    # Handle Paho MQTT v2 vs v1 CallbackAPIVersion compatibility
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    else:
        client = mqtt.Client()

    if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

    def on_connect(client_inst, userdata, flags, reason_code, properties=None):
        is_success = (reason_code == 0) if isinstance(reason_code, int) else not getattr(reason_code, "is_failure", True)
        if is_success:
            logger.info(
                "Successfully connected to MQTT broker at %s:%d",
                settings.MQTT_BROKER_HOST,
                settings.MQTT_BROKER_PORT,
            )
            client_inst.subscribe(settings.MQTT_TOPIC)
            logger.info("Subscribed to MQTT topic pattern: '%s'", settings.MQTT_TOPIC)
        else:
            logger.warning("MQTT broker connection failed with code: %s", reason_code)


    def on_message(client_inst, userdata, msg):
        try:
            handle_mqtt_message(topic=msg.topic, payload_bytes=msg.payload)
        except Exception as exc:
            logger.error("Unhandled exception processing MQTT message on '%s': %s", msg.topic, exc)

    def on_disconnect(client_inst, userdata, rc, properties=None):
        if rc != 0:
            logger.warning("Unexpected disconnection from MQTT broker (rc=%s). Reconnect loop active.", rc)
        else:
            logger.info("Disconnected from MQTT broker cleanly.")

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    return client


def start_mqtt_subscriber() -> mqtt.Client | None:
    """Start the MQTT subscriber in a background thread.

    Non-blocking. If the MQTT broker is unreachable or fails to connect,
    logs a warning without raising an exception so FastAPI application startup
    is never blocked.
    """
    global _mqtt_client

    if _mqtt_client is not None:
        logger.info("MQTT subscriber is already running.")
        return _mqtt_client

    client = create_mqtt_client()

    try:
        logger.info(
            "Attempting to connect to MQTT broker at %s:%d...",
            settings.MQTT_BROKER_HOST,
            settings.MQTT_BROKER_PORT,
        )
        client.connect(
            host=settings.MQTT_BROKER_HOST,
            port=settings.MQTT_BROKER_PORT,
            keepalive=60,
        )
        client.loop_start()
        _mqtt_client = client
        logger.info("MQTT background network loop started.")
        return client
    except Exception as exc:
        logger.warning(
            "Could not connect to MQTT broker at %s:%d (%s). "
            "FastAPI startup proceeding. Telemetry ingestion via MQTT will be unavailable until broker is reachable.",
            settings.MQTT_BROKER_HOST,
            settings.MQTT_BROKER_PORT,
            exc,
        )
        _mqtt_client = None
        return None


def stop_mqtt_subscriber() -> None:
    """Stop the MQTT background loop and disconnect cleanly upon FastAPI shutdown."""
    global _mqtt_client

    if _mqtt_client is not None:
        logger.info("Stopping MQTT subscriber background loop...")
        try:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
        except Exception as exc:
            logger.warning("Error stopping MQTT client: %s", exc)
        finally:
            _mqtt_client = None
        logger.info("MQTT subscriber stopped cleanly.")