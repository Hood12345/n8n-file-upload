from flask import Flask, request, send_from_directory, jsonify, abort, render_template_string
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import uuid
import time
import magic
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
limiter = Limiter(app, key_func=get_remote_address)

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
    return parts[0], int(parts[1]) if len(parts) > 1 else 0

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
        # MIME type check
        mime = magic.from_buffer(file.read(2048), mime=True)
        if not (mime.startswith("video/") or mime.startswith("image/")):
            return jsonify({"error": "Invalid MIME type"}), 400
        file.seek(0)

        ext = file.filename.rsplit('.', 1)[1].lower()
        expiry = get_expiry_timestamp()
        unique_name = f"{uuid.uuid4()}__{expiry}.{ext}"
        secure_name = secure_filename(unique_name)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        file.save(file_path)

        file_url = f"{request.host_url}static/{secure_name}"
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

    # Render a UI with a download link in case auto-download doesn't work
    download_html = f'''
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>Download File</title></head>
    <body style="text-align:center;margin-top:40px;">
      <h2>Your file is ready to download</h2>
      <a href="/file-download/{filename}" download>Click here to download</a>
    </body></html>
    '''
    return render_template_string(download_html)

# --- Actual forced download ---
@app.route('/file-download/<path:filename>', methods=['GET'])
def file_download(filename):
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
