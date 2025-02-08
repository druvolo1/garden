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

def start_threads():
    eventlet.spawn(background_task)
    print("DEBUG: background_task spawned")

@app.route("/")
def index():
    return "Hello"

# Start background threads as soon as the module is imported.
start_threads()

if __name__ == "__main__":
    app.run("0.0.0.0", 8000, debug=False)
