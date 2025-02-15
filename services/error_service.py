# File: services/error_service.py

error_codes = {
    "PH_USB_OFFLINE": "pH probe not found or offline",
    "RELAY_USB_OFFLINE": "Relay device not found or offline",
    "PH_OUT_OF_RANGE": "pH reading is outside configured min/max range"
    # You can add more as needed...
}

# We store the active error codes in a set so we don't add duplicates.
_error_state = set()

def set_error(code):
    """
    Mark a specific error code as active.
    """
    if code in error_codes:
        _error_state.add(code)

def clear_error(code):
    """
    Mark the error code as resolved.
    """
    if code in _error_state:
        _error_state.remove(code)

def get_current_errors():
    """
    Return a list of user-friendly error messages for all active error codes.
    """
    return [error_codes[code] for code in _error_state]
