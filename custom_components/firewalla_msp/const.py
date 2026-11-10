"""Constants for the Firewalla MSP integration."""
from __future__ import annotations

DOMAIN = "firewalla_msp"

CONF_MSP_DOMAIN = "msp_domain"
CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TRACKED_DEVICES = "tracked_devices"

# Alarms and devices are polled every scan_interval. Boxes and rules change
# rarely, so they're fetched on their own slower cadence. At the defaults this
# is ~68 requests/hour instead of 240, which keeps clear of the MSP rate limit.
DEFAULT_SCAN_INTERVAL = 120  # seconds
MIN_SCAN_INTERVAL = 60
BOXES_INTERVAL = 600  # seconds
RULES_INTERVAL = 1800  # seconds
ALARM_FETCH_LIMIT = 50

# Back-off after HTTP 429 when the server sends no Retry-After header.
BACKOFF_INITIAL = 120  # seconds
BACKOFF_MAX = 1800  # seconds

EVENT_ALARM = f"{DOMAIN}_alarm"

ALARM_STATUS_ACTIVE = 1

# https://docs.firewalla.net/data-models/alarm/
ALARM_TYPES: dict[int, str] = {
    1: "Security Activity",
    2: "Abnormal Upload",
    3: "Large Bandwidth Usage",
    4: "Monthly Data Plan",
    5: "New Device",
    6: "Device Back Online",
    7: "Device Offline",
    8: "Video Activity",
    9: "Gaming Activity",
    10: "Porn Activity",
    11: "VPN Activity",
    12: "VPN Connection Restored",
    13: "VPN Connection Error",
    14: "Open Port",
    15: "Internet Connectivity Update",
    16: "Large Upload",
}

# WAN status values used in type 15 alarms
WAN_STATUS: dict[int, str] = {1: "connected", 2: "standby", 3: "disconnected"}

PLATFORMS = ["binary_sensor", "sensor", "switch"]
