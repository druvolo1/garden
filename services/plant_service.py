# File: services/plant_service.py
from datetime import datetime

def get_weeks_since_start(plant_info):
    """
    Example function that calculates weeks from plant_info's start_date.
    plant_info might look like {"name": "Tomatoes", "start_date": "2025-02-14"}.
    """
    if not plant_info or "start_date" not in plant_info:
        return 0
    start_str = plant_info["start_date"]
    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d")
        now = datetime.now()
        diff = now - start_date
        if diff.days < 0:
            return 0
        return diff.days // 7  # Return whole weeks
    except ValueError:
        return 0
