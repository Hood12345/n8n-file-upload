from flask import Flask, request, send_from_directory, jsonify
import os
import uuid

UPLOAD_FOLDER = "static"
app = Flask(__name__)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    base_url = request.host_url.rstrip("/")
    return jsonify({
        "success": True,
        "url": f"{base_url}/static/{filename}"
    })

@app.route("/static/<filename>")
def serve_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)
