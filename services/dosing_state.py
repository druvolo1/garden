# dosing_state.py
class DosingState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.active_dosing_task = None
            cls._instance.active_relay_port = None
            cls._instance.active_dosing_type = None
            cls._instance.active_dosing_amount = None
            cls._instance.active_start_time = None
            cls._instance.active_duration = None
        return cls._instance

state = DosingState()  # Export the instance