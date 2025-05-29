from flask import Flask, request, send_file, jsonify
from werkzeug.utils import secure_filename
from urllib.parse import unquote
import os
import uuid
import time
import threading

# --- Config ---
UPLOAD_FOLDER = os.path.join(os.getcwd(), "static")
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE_MB = 500
FILE_EXPIRY_SECONDS = 86400  # 24 hours

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE_MB * 1024 * 1024

# Create folder if not exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_expiry_timestamp():
    return int(time.time()) + FILE_EXPIRY_SECONDS

def extract_filename_parts(filename):
    parts = filename.split("__")
    return parts[0], int(parts[1].split('.')[0]) if len(parts) > 1 else 0

# --- Upload Endpoint ---
@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file') or request.files.get('data')
    if not file or file.filename == '':
        return jsonify({"error": "No file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    expiry = get_expiry_timestamp()
    unique_name = f"{uuid.uuid4()}__{expiry}.{ext}"
    safe_name = secure_filename(unique_name)
    path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    file.save(path)

    # ✅ Always return query URL
    url = f"{request.url_root.replace('http://', 'https://')}download?file={safe_name}"
    return jsonify({"success": True, "url": url})

# --- iPhone-Safe Download Endpoint ---
@app.route('/download', methods=['GET'])
def download():
    raw = request.args.get("file")
    if not raw:
        return "Missing file param", 400

    filename = unquote(raw)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        _, expiry = extract_filename_parts(filename)
        if time.time() > expiry:
            if os.path.exists(path):
                os.remove(path)
            return "File expired", 410

        if not os.path.isfile(path):
            return "File not found", 404

        return send_file(path, as_attachment=True)
    except Exception as e:
        return f"Error: {str(e)}", 500

# --- Auto-delete old files ---
def cleanup():
    while True:
        time.sleep(300)
        for fname in os.listdir(UPLOAD_FOLDER):
            if "__" in fname:
                try:
                    _, exp = extract_filename_parts(fname)
                    if time.time() > exp:
                        os.remove(os.path.join(UPLOAD_FOLDER, fname))
                except:
                    continue

threading.Thread(target=cleanup, daemon=True).start()

# --- Healthcheck ---
@app.route('/')
def health():
    return jsonify({"status": "running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
