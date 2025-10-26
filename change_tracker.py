"""
Change Tracker Module
Tracks the last sent values and detects changes to minimize bandwidth usage.
Only sends updates when values actually change.
"""

import json
import copy
from threading import Lock

# Thread-safe storage for last sent values
_last_sent = {
    "ph": None,
    "ec": None,
    "water_level": None,
    "valve_states": {},
    "settings": None,
    "plant_info": None,
    "dosage_info": None,
}

_lock = Lock()

def _deep_compare(obj1, obj2):
    """Deep comparison of two objects, handling nested dicts and lists."""
    if type(obj1) != type(obj2):
        return False
    
    if isinstance(obj1, dict):
        if set(obj1.keys()) != set(obj2.keys()):
            return False
        return all(_deep_compare(obj1[k], obj2[k]) for k in obj1.keys())
    
    if isinstance(obj1, list):
        if len(obj1) != len(obj2):
            return False
        return all(_deep_compare(a, b) for a, b in zip(obj1, obj2))
    
    return obj1 == obj2

def reset_tracker():
    """Reset all tracked values (called on device connect/reconnect)."""
    global _last_sent
    with _lock:
        _last_sent = {
            "ph": None,
            "ec": None,
            "water_level": None,
            "valve_states": {},
            "settings": None,
            "plant_info": None,
            "dosage_info": None,
        }
        print("[CHANGE_TRACKER] Reset all tracked values")

def check_ph_changed(current_ph):
    """Check if pH value has changed from last sent."""
    with _lock:
        if current_ph is None:
            return False
        
        last_ph = _last_sent["ph"]
        if last_ph is None or current_ph != last_ph:
            _last_sent["ph"] = current_ph
            return True
        return False

def check_ec_changed(current_ec):
    """Check if EC value has changed from last sent."""
    with _lock:
        if current_ec is None:
            return False
        
        last_ec = _last_sent["ec"]
        if last_ec is None or current_ec != last_ec:
            _last_sent["ec"] = current_ec
            return True
        return False

def check_water_level_changed(water_level_data):
    """Check if water level sensor states have changed."""
    with _lock:
        if not water_level_data:
            return False
        
        # Extract just the triggered states for comparison
        current_state = {
            "sensor1": water_level_data.get("sensor1", {}).get("triggered", False),
            "sensor2": water_level_data.get("sensor2", {}).get("triggered", False),
            "sensor3": water_level_data.get("sensor3", {}).get("triggered", False),
        }
        
        last_state = _last_sent["water_level"]
        if last_state is None or not _deep_compare(current_state, last_state):
            _last_sent["water_level"] = current_state
            return True
        return False

def check_valve_changed(valve_label, valve_status):
    """Check if a specific valve state has changed."""
    with _lock:
        last_status = _last_sent["valve_states"].get(valve_label)
        if last_status is None or valve_status != last_status:
            _last_sent["valve_states"][valve_label] = valve_status
            return True
        return False

def check_settings_changed(settings_data):
    """Check if settings have changed."""
    with _lock:
        # Compare only relevant settings fields (exclude timestamps, etc.)
        current_settings = {
            "system_name": settings_data.get("system_name"),
            "fill_valve_label": settings_data.get("fill_valve_label"),
            "drain_valve_label": settings_data.get("drain_valve_label"),
            "usb_roles": settings_data.get("usb_roles"),
        }
        
        last_settings = _last_sent["settings"]
        if last_settings is None or not _deep_compare(current_settings, last_settings):
            _last_sent["settings"] = copy.deepcopy(current_settings)
            return True
        return False

def check_plant_info_changed(plant_info_data):
    """Check if plant info has changed."""
    with _lock:
        if not plant_info_data:
            return False
        
        current_plant = {
            "name": plant_info_data.get("name"),
            "start_date": plant_info_data.get("start_date"),
        }
        
        last_plant = _last_sent["plant_info"]
        if last_plant is None or not _deep_compare(current_plant, last_plant):
            _last_sent["plant_info"] = copy.deepcopy(current_plant)
            return True
        return False

def check_dosage_changed(dosage_data):
    """Check if dosage calculations have changed."""
    with _lock:
        if not dosage_data:
            return False
        
        # Compare dosage amounts and pH values
        current_dosage = {
            "ph_up_amount": dosage_data.get("ph_up_amount"),
            "ph_down_amount": dosage_data.get("ph_down_amount"),
            "current_ph": dosage_data.get("current_ph"),
            "ph_target": dosage_data.get("ph_target"),
        }
        
        last_dosage = _last_sent["dosage_info"]
        if last_dosage is None or not _deep_compare(current_dosage, last_dosage):
            _last_sent["dosage_info"] = copy.deepcopy(current_dosage)
            return True
        return False

def get_all_changes(status_payload):
    """
    Check all fields in status_payload and return a list of change messages to send.
    Returns empty list if nothing changed.
    """
    changes = []
    
    # Check pH
    current_ph = status_payload.get("current_ph")
    if check_ph_changed(current_ph):
        changes.append({
            "type": "ph_update",
            "value": current_ph
        })
    
    # Check EC
    current_ec = status_payload.get("current_ec")
    if check_ec_changed(current_ec):
        changes.append({
            "type": "ec_update",
            "value": current_ec
        })
    
    # Check water level
    water_level = status_payload.get("water_level")
    if water_level and check_water_level_changed(water_level):
        changes.append({
            "type": "water_level_update",
            "sensor1": {
                "triggered": water_level.get("sensor1", {}).get("triggered", False),
                "label": water_level.get("sensor1", {}).get("label", "Full")
            },
            "sensor2": {
                "triggered": water_level.get("sensor2", {}).get("triggered", False),
                "label": water_level.get("sensor2", {}).get("label", "Low")
            },
            "sensor3": {
                "triggered": water_level.get("sensor3", {}).get("triggered", False),
                "label": water_level.get("sensor3", {}).get("label", "Empty")
            }
        })
    
    # Check valve states
    valve_info = status_payload.get("valve_info", {})
    valve_relays = valve_info.get("valve_relays", {})
    for valve_label, valve_data in valve_relays.items():
        valve_status = valve_data.get("status", "off")
        if check_valve_changed(valve_label, valve_status):
            changes.append({
                "type": "valve_update",
                "label": valve_label,
                "status": valve_status
            })
    
    # Check settings
    settings = status_payload.get("settings", {})
    if check_settings_changed(settings):
        changes.append({
            "type": "settings_update",
            "system_name": settings.get("system_name"),
            "fill_valve_label": settings.get("fill_valve_label"),
            "drain_valve_label": settings.get("drain_valve_label"),
            "usb_roles": settings.get("usb_roles"),
        })
    
    # Check plant info
    plant_info = settings.get("plant_info", {})
    if check_plant_info_changed(plant_info):
        changes.append({
            "type": "plant_info_update",
            "name": plant_info.get("name"),
            "start_date": plant_info.get("start_date"),
        })
    
    # Check dosage info
    dosage_info = status_payload.get("dosage_info")
    if dosage_info and check_dosage_changed(dosage_info):
        changes.append({
            "type": "dosage_update",
            "ph_up_amount": dosage_info.get("ph_up_amount"),
            "ph_down_amount": dosage_info.get("ph_down_amount"),
            "current_ph": dosage_info.get("current_ph"),
            "ph_target": dosage_info.get("ph_target"),
        })
    
    return changes
