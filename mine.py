# server.py

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import json
import uuid
import logging
from datetime import datetime, timedelta
import jwt
from functools import wraps
from data_source import DataSource  # Importujte DataSource z data_source.py

# Konfigurace
SECRET_KEY = 'your_secret_key'  # Nahraďte silným tajným klíčem
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

# Inicializace aplikace
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
CORS(app)  # Povolení CORS pro přístup z různých domén
socketio = SocketIO(app, cors_allowed_origins="*")

# Konfigurace logování
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Zajištění existence upload složky
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Inicializace datového zdroje
data_source = DataSource()

# Autentizační dekorátor
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        if not token:
            return jsonify({'message': 'Token is missing!'}), 403
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user = data['user']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 403
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token is invalid!'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

# Endpoint pro hlavní stránku
@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>Server Pracovních Záznamů</title>
        </head>
        <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 50px;">
            <h1>Server pro aplikaci pracovních záznamů běží</h1>
            <p>Pod správou <strong>AdaSoft</strong>.</p>
        </body>
    </html>
    """

# Endpoint pro přihlášení a získání tokenu
@app.route('/login', methods=['POST'])
def login():
    auth = request.json
    name = auth.get('name', '').strip()
    if not name:
        return jsonify({'message': 'Name is required'}), 400
    if name in data_source.get_workers():
        token = jwt.encode({
            'user': name,
            'exp': datetime.utcnow() + timedelta(hours=1)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({'token': token}), 200
    return jsonify({'message': 'Worker not found'}), 404

# Nový endpoint pro získání tokenu pomocí API klíče
@app.route('/get_token', methods=['POST'])
def get_token():
    api_key = request.headers.get('x-api-key')
    if not api_key:
        return jsonify({'message': 'API key is missing!'}), 400
    if data_source.verify_api_key(api_key):
        # Vygenerovat token pro API klíč
        token = jwt.encode({
            'user': 'mobile_app',
            'exp': datetime.utcnow() + timedelta(hours=1)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({'token': token}), 200
    else:
        return jsonify({'message': 'Invalid API key!'}), 403

# Endpoint pro přidání pracovníka
@app.route('/add_worker', methods=['POST'])
@token_required
def add_worker(current_user):
    data = request.json
    worker_name = data.get("worker", "").strip()
    if not worker_name:
        return jsonify({"status": "error", "message": "Worker name is required"}), 400
    if worker_name in data_source.get_workers():
        return jsonify({"status": "error", "message": "Worker already exists"}), 400
    data_source.add_worker(worker_name)
    socketio.emit('update_workers', data_source.get_workers(), broadcast=True)
    return jsonify({"status": "success", "workers": data_source.get_workers()}), 200

# Endpoint pro odstranění pracovníka
@app.route('/remove_worker', methods=['DELETE'])
@token_required
def remove_worker(current_user):
    data = request.json
    worker_name = data.get("worker", "").strip()
    if not worker_name:
        return jsonify({"status": "error", "message": "Worker name is required"}), 400
    if worker_name not in data_source.get_workers():
        return jsonify({"status": "error", "message": "Worker not found"}), 404
    data_source.remove_worker(worker_name)
    socketio.emit('update_workers', data_source.get_workers(), broadcast=True)
    return jsonify({"status": "success", "workers": data_source.get_workers()}), 200

# Endpoint pro přidání projektu
@app.route('/add_project', methods=['POST'])
@token_required
def add_project(current_user):
    data = request.json
    project_name = data.get("project", "").strip()
    if not project_name:
        return jsonify({"status": "error", "message": "Project name is required"}), 400
    if project_name in data_source.get_projects():
        return jsonify({"status": "error", "message": "Project already exists"}), 400
    data_source.add_project(project_name)
    socketio.emit('update_projects', data_source.get_projects(), broadcast=True)
    return jsonify({"status": "success", "projects": data_source.get_projects()}), 200

# Endpoint pro odstranění projektu
@app.route('/remove_project', methods=['DELETE'])
@token_required
def remove_project(current_user):
    data = request.json
    project_name = data.get("project", "").strip()
    if not project_name:
        return jsonify({"status": "error", "message": "Project name is required"}), 400
    if project_name not in data_source.get_projects():
        return jsonify({"status": "error", "message": "Project not found"}), 404
    data_source.remove_project(project_name)
    socketio.emit('update_projects', data_source.get_projects(), broadcast=True)
    return jsonify({"status": "success", "projects": data_source.get_projects()}), 200

# Endpoint pro přidání záznamu
@app.route('/add_record', methods=['POST'])
@token_required
def add_record(current_user):
    data = request.json
    # Validace struktury dat
    required_fields = ["worker", "project", "date", "start_time", "break_start", "break_end", "end_time", "hours", "description"]
    for field in required_fields:
        if field not in data:
            return jsonify({"status": "error", "message": f"Field '{field}' is missing"}), 400
    success = data_source.add_record(data)
    if success:
        socketio.emit('new_record', data, broadcast=True)
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error", "message": "Failed to add record. Ensure worker and project exist."}), 400

# Endpoint pro získání všech záznamů
@app.route('/records_all', methods=['GET'])
@token_required
def get_all_records(current_user):
    records = data_source.get_records_for_project(None)  # Získání všech záznamů bez filtru
    return jsonify({"records": records}), 200

# Endpoint pro nahrání fotografie k projektu
@app.route('/upload_photo', methods=['POST'])
@token_required
def upload_photo(current_user):
    if 'photo' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['photo']
    project_name = request.form.get('project', '').strip()

    if not project_name:
        return jsonify({"status": "error", "message": "Project name is required"}), 400

    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    if file and allowed_file(file.filename):
        project_folder = os.path.join(app.config['UPLOAD_FOLDER'], project_name)
        if not os.path.exists(project_folder):
            os.makedirs(project_folder)
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        file_path = os.path.join(project_folder, filename)
        file.save(file_path)

        # Přidání cesty k fotografii do projektu
        relative_path = os.path.join(project_name, filename)
        data_source.add_photo_to_project(project_name, relative_path)
        socketio.emit('update_project_photos', {"project": project_name, "photos": data_source.get_photos_for_project(project_name)}, broadcast=True)

        return jsonify({"status": "success", "filename": relative_path}), 200
    else:
        return jsonify({"status": "error", "message": "File type not allowed"}), 400

# Endpoint pro získání fotografií k projektu
@app.route('/project_photos/<project_name>', methods=['GET'])
@token_required
def get_project_photos(current_user, project_name):
    photos = data_source.get_photos_for_project(project_name)
    return jsonify({"photos": photos}), 200

# Endpoint pro stahování fotografie
@app.route('/download_photo/<path:filename>', methods=['GET'])
@token_required
def download_photo(current_user, filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# Funkce pro kontrolu povolených typů souborů
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# SocketIO události
@socketio.on('connect')
def handle_connect():
    logger.info('Nový klient připojen.')
    emit('message', {'data': 'Připojeno k serveru.'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Klient odpojen.')

# Spuštění serveru
if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000)
    logger.info("API server běží na http://0.0.0.0:5000")
