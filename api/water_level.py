# File: api/water_level.py
from flask import Blueprint, jsonify, request
from services.water_level_service import get_water_level_status

water_level_blueprint = Blueprint('water_level', __name__)

@water_level_blueprint.route('/', methods=['GET'])
def get_water_level():
    """
    Get the current status of the water level sensors.
    """
    return jsonify(get_water_level_status())

# If you want to update sensor pins directly here (optional):
# @water_level_blueprint.route('/', methods=['POST'])
# def update_water_level_config():
#     # parse JSON, update settings, etc.
#     pass
