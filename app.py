from flask import Flask, request, send_from_directory, jsonify, abort, render_template_string
from werkzeug.utils import secure_filename, safe_join
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from urllib.parse import unquote
import os
import uuid
import time
import threading

# --- Config ---
UPLOAD_FOLDER = os.path.join(os.getcwd(), "static")
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE_MB = 500
FILE_EXPIRY_SECONDS = 3600  # 1 hour expiry

# --- App setup ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE_MB * 1024 * 1024

# --- Rate Limiting ---
limiter = Limiter(get_remote_address)
limiter.init_app(app)

# --- Create static directory if missing ---
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Enable CORS ---
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_expiry_timestamp():
    return int(time.time()) + FILE_EXPIRY_SECONDS

def extract_filename_parts(filename):
    parts = filename.split("__")
    return parts[0], int(parts[1].split('.')[0]) if len(parts) > 1 else 0

# --- Upload endpoint ---
@app.route('/upload', methods=['POST'])
@limiter.limit("10/minute")
def upload_file():
    file = request.files.get('file') or request.files.get('data')
    if not file:
        return jsonify({"error": "No file part in request"}), 400
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if file and allowed_file(file.filename):
        if not (file.mimetype.startswith("video/") or file.mimetype.startswith("image/")):
            return jsonify({"error": "Invalid MIME type"}), 400

        ext = file.filename.rsplit('.', 1)[1].lower()
        expiry = get_expiry_timestamp()
        unique_name = f"{uuid.uuid4()}__{expiry}.{ext}"
        secure_name = secure_filename(unique_name)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        file.save(file_path)

        # ✅ SAFER for iOS: use query string version
        file_url = f"{request.url_root.replace('http://', 'https://')}file-download?file={secure_name}"
        return jsonify({"success": True, "url": file_url}), 200
    else:
        return jsonify({"error": "File type not allowed"}), 400

# --- Static access with expiry check ---
@app.route('/static/<path:filename>', methods=['GET'])
def serve_static(filename):
    if ".." in filename or "/" in filename:
        abort(400, description="Invalid filename")
    name_part, expiry_timestamp = extract_filename_parts(filename)
    if time.time() > expiry_timestamp:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        app.logger.warning(f"[EXPIRED] {filename} expired and removed")
        abort(410, description="File has expired")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- /file-download using PATH (still here for legacy) ---
@app.route('/file-download/<path:filename>', methods=['GET'])
def file_download_path(filename):
    filename = unquote(filename)
    file_path = safe_join(app.config['UPLOAD_FOLDER'], filename)

    print("[DEBUG] PATH - Incoming filename:", filename)
    print("[DEBUG] PATH - File path:", file_path)
    print("[DEBUG] PATH - Exists:", os.path.isfile(file_path))

    if not file_path or not os.path.isfile(file_path):
        return f"File not found<br>Decoded filename: {filename}<br>Path: {file_path}", 404

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=f"download.{filename.rsplit('.', 1)[1]}"
    )

# --- ✅ SAFER /file-download?file=... endpoint ---
@app.route('/file-download', methods=['GET'])
def file_download_query():
    raw_filename = request.args.get("file")
    if not raw_filename:
        return "Missing file parameter", 400

    filename = unquote(raw_filename)
    file_path = safe_join(app.config['UPLOAD_FOLDER'], filename)

    print("[DEBUG] QUERY - Filename:", filename)
    print("[DEBUG] QUERY - File path:", file_path)
    print("[DEBUG] QUERY - Exists:", os.path.isfile(file_path))

    if not file_path or not os.path.isfile(file_path):
        return f"File not found<br>Decoded filename: {filename}<br>Path: {file_path}", 404

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=f"download.{filename.rsplit('.', 1)[1]}"
    )

# --- /force-download endpoint (still available) ---
@app.route('/force-download/<path:filename>', methods=['GET', 'POST'])
def force_download(filename):
    filename = unquote(filename)
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=f"download.{filename.rsplit('.', 1)[1]}"
    )

# --- Background cleanup thread ---
def cleanup_expired_files():
    while True:
        time.sleep(300)
        for fname in os.listdir(UPLOAD_FOLDER):
            if "__" in fname:
                try:
                    _, expiry = extract_filename_parts(fname)
                    if time.time() > expiry:
                        os.remove(os.path.join(UPLOAD_FOLDER, fname))
                except Exception:
                    continue

cleanup_thread = threading.Thread(target=cleanup_expired_files, daemon=True)
cleanup_thread.start()

# --- Healthcheck ---
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "running"}), 200

# --- Launch ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
