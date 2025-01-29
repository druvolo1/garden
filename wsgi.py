# File: wsgi.py

import eventlet
eventlet.monkey_patch()  # Must occur first, so eventlet patches Python libs

from app import app  # Now import your Flask app from app.py
# from app import start_threads if you want to call it here
# but typically we'll rely on post_fork or a single call at the bottom.

# If you do local debugging with "python wsgi.py":
if __name__ == "__main__":
    # This is only for a quick single-process dev run
    # You can optionally do:
    # from app import start_threads
    # start_threads()
    app.run(host="0.0.0.0", port=5000, debug=True)
