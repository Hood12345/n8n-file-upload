from flask import Flask, request, send_from_directory, jsonify, abort, render_template_string, redirect
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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
limiter = Limiter(key_func=get_remote_address)
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
    if 'data' not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files['data']

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if file and allowed_file(file.filename):
        # MIME type check using file.mimetype
        if not (file.mimetype.startswith("video/") or file.mimetype.startswith("image/")):
            return jsonify({"error": "Invalid MIME type"}), 400

        ext = file.filename.rsplit('.', 1)[1].lower()
        expiry = get_expiry_timestamp()
        unique_name = f"{uuid.uuid4()}__{expiry}.{ext}"
        secure_name = secure_filename(unique_name)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        file.save(file_path)

        file_url = f"{request.url_root}static/{secure_name}"
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
        abort(410, description="File has expired")

    # Redirect to file-download which triggers browser download
    return redirect(f"/file-download/{filename}", code=302)

# --- Actual forced download ---
@app.route('/file-download/<path:filename>', methods=['GET'])
def file_download(filename):
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
        <a class="download-button" href="/force-download/{filename}">Download File</a>
        <script>
            window.location.href = "/force-download/{filename}";
        </script>
    </body>
    </html>
    """
    return render_template_string(fallback_ui)

# --- Force-download endpoint (triggered via JS or button) ---
@app.route('/force-download/<path:filename>', methods=['GET'])
def force_download(filename):
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        download_name=f"download.{filename.rsplit('.', 1)[1]}"
    )

# --- Cleanup expired files in background ---
def cleanup_expired_files():
    while True:
        time.sleep(300)  # Check every 5 minutes
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
