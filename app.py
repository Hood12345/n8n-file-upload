from flask import Flask, request, send_from_directory, jsonify
import os
import uuid

# Create the app
app = Flask(__name__)

# Create the upload folder if it doesn't exist
UPLOAD_FOLDER = "static"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Upload route
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    # Generate unique filename
    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    # Generate public download link
    base_url = request.host_url.rstrip("/")
    return jsonify({
        "success": True,
        "url": f"{base_url}/static/{filename}"
    })

# Serve uploaded files
@app.route("/static/<filename>")
def serve_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ✅ This is the fix that allows Railway to connect properly
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
