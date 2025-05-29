from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from urllib.parse import unquote
import os
import uuid
import threading
import time
from functools import wraps

# --- API Key Protection ---
API_KEY = os.getenv("UPLOAD_API_KEY", "a920f5e9cb7d4e2eb8a1f0b25a89e0c9")  # Replace or set in Railway

def require_api_key():
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            key = request.headers.get("X-API-Key") or request.args.get("api_key")
            if key != API_KEY:
                return jsonify({"error": "Forbidden: Invalid API Key"}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator

# --- Config ---
UPLOAD_FOLDER = os.path.join(os.getcwd(), "static")
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE_MB = 500

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE_MB * 1024 * 1024

# Create folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Upload endpoint ---
@app.route('/upload', methods=['POST'])
@require_api_key()
def upload():
    file = request.files.get('file') or request.files.get('data')
    if not file or file.filename == '':
        return jsonify({"error": "No file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid.uuid4()}.{ext}"
    safe_name = secure_filename(unique_name)
    path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    file.save(path)

    url = f"{request.url_root.replace('http://', 'https://')}download?file={safe_name}"
    return jsonify({"success": True, "url": url})

# --- Download endpoint (no expiry) ---
@app.route('/download', methods=['GET'])
@require_api_key()
def download():
    raw = request.args.get("file")
    if not raw:
        return "Missing file param", 400

    filename = unquote(raw)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    print("[DEBUG] Requested file:", filename)
    print("[DEBUG] File exists:", os.path.isfile(path))

    if not os.path.isfile(path):
        return "File not found", 404

    return send_file(path, as_attachment=True)

# --- Cleanup thread (optional: remove old files after 24h) ---
def cleanup():
    while True:
        time.sleep(3600)  # check every hour
        cutoff = time.time() - (24 * 3600)  # 24 hours ago
        for fname in os.listdir(UPLOAD_FOLDER):
            try:
                fpath = os.path.join(UPLOAD_FOLDER, fname)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    print(f"[CLEANUP] Removed: {fname}")
            except:
                continue

threading.Thread(target=cleanup, daemon=True).start()

# --- Healthcheck ---
@app.route('/')
def health():
    return jsonify({"status": "running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
