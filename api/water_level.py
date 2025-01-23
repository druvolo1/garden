from flask import Blueprint, jsonify
from services.water_level_service import get_water_level_status

# Create the Blueprint for water level API
water_level_blueprint = Blueprint('water_level', __name__)

@water_level_blueprint.route('/', methods=['GET'])
def get_water_level():
    """
    Get the current status of the water level sensors.
    """
    return jsonify(get_water_level_status())
