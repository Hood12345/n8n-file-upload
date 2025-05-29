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
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE_MB * 1024 * 1024  # 500MB limit

# --- Rate Limiting ---
limiter = Limiter(get_remote_address)
limiter.init_app(app)

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

        file_url = f"{request.url_root.replace('http://', 'https://')}file-download/{secure_name}"
        return jsonify({"success": True, "url": file_url}), 200
    else:
        return jsonify({"error": "File type not allowed"}), 400

# --- Serve files with forced download and expiry check ---
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

# --- Actual forced download with UI fallback ---
@app.route('/file-download/<path:filename>', methods=['GET'])
def file_download(filename):
    filename = unquote(filename)  # iOS fix
    file_path = safe_join(app.config['UPLOAD_FOLDER'], filename)
    if not file_path or not os.path.isfile(file_path):
        app.logger.error(f"[NOT FOUND] Tried to download missing file: {filename}")
        abort(404, description="File not found")

    is_ios_safari = "Safari" in request.headers.get('User-Agent', '') and "Mobile" in request.headers.get('User-Agent', '')

    if is_ios_safari:
        fallback_ui = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Download File</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 40px; text-align: center; }}
                a.download-button {{
                    display: inline-block;
                    padding: 12px 24px;
                    margin-top: 20px;
                    font-size: 18px;
                    color: white;
                    background-color: #007BFF;
                    text-decoration: none;
                    border-radius: 6px;
                }}
            </style>
        </head>
        <body>
            <h2>Your download will begin shortly.</h2>
            <p>If it doesn't, click the button below:</p>
            <a class="download-button" href="/force-download/{filename}" download>Download File</a>
        </body>
        </html>
        """
        return render_template_string(fallback_ui)
    else:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'],
            filename,
            as_attachment=True,
            download_name=f"download.{filename.rsplit('.', 1)[1]}"
        )

# --- Force-download endpoint ---
@app.route('/force-download/<path:filename>', methods=['GET'])
def force_download(filename):
    filename = unquote(filename)  # iOS fix
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=f"download.{filename.rsplit('.', 1)[1]}"
    )

# --- Cleanup expired files in background ---
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
