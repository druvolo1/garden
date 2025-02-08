import eventlet
eventlet.monkey_patch()

from flask import Flask
app = Flask(__name__)

stop_event = eventlet.event.Event()

def background_task():
    print("DEBUG: Entered background_task")
    while not stop_event.ready():
        print("DEBUG: background_task still alive")
        eventlet.sleep(2)

@app.route("/")
def index():
    return "Hello"

def start_threads():
    eventlet.spawn(background_task)
    print("DEBUG: background_task spawned")

if __name__ == "__main__":
    start_threads()
    # Use Eventlet's WSGI server instead of app.run()
    from eventlet import wsgi, listen
    wsgi.server(listen(("0.0.0.0", 8000)), app)
