def post_worker_init(worker):
    from app import start_serial_reader 
    start_serial_reader()

def post_fork(server, worker):
    from app import start_threads
    print("[Gunicorn] post_fork: Starting background threads...")
    start_threads()