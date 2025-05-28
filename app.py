from flask import Flask, request, send_from_directory, jsonify
from werkzeug.utils import secure_filename
import os
import uuid

# --- Config ---
UPLOAD_FOLDER = os.path.join(os.getcwd(), "static")
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE_MB = 500

# --- App setup ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE_MB * 1024 * 1024  # 500MB limit

# --- Create static directory if missing ---
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Enable CORS for mobile/browser download ---
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Upload endpoint ---
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'data' not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files['data']

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        unique_name = f"{uuid.uuid4()}.{ext}"
        secure_name = secure_filename(unique_name)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        file.save(file_path)

        file_url = f"{request.host_url}static/{secure_name}"
        return jsonify({"success": True, "url": file_url}), 200
    else:
        return jsonify({"error": "File type not allowed"}), 400

# --- Serve files for download ---
@app.route('/static/<path:filename>', methods=['GET'])
def serve_static(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# --- Healthcheck ---
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "running"}), 200

# --- Launch ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
