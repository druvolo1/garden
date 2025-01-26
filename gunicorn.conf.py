def post_worker_init(worker):
    from app import start_serial_reader 
    start_serial_reader()
