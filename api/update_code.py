# Example: api/update_code.py

import subprocess
import os
from flask import Blueprint, jsonify, request

update_code_blueprint = Blueprint('update_code', __name__)

REPO_DIR = os.path.join(os.getcwd(), "your_repo_folder")  
# or the absolute path to your application’s Git folder

@update_code_blueprint.route('/pull', methods=['POST'])
def pull_latest_code():
    try:
        # cd into your repo folder
        output = subprocess.check_output(["git", "pull"], cwd=REPO_DIR)
        # success
        return jsonify({
            "status": "success",
            "output": output.decode("utf-8")
        })
    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "failure",
            "error": str(e),
            "output": e.output.decode("utf-8") if e.output else ""
        }), 500
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500
