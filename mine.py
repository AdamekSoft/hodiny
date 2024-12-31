from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import json
import uuid
import logging
from datetime import datetime, timedelta
import requests
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

# Endpoint pro přidání pracovníka
@app.route('/add_worker', methods=['POST'])
def add_worker():
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
def remove_worker():
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
def add_project():
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
def remove_project():
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
def add_record():
    data = request.json
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
def get_all_records():
    records = data_source.get_records_for_project(None)
    return jsonify({"records": records}), 200

# Endpoint pro nahrání fotografie k projektu
@app.route('/upload_photo', methods=['POST'])
def upload_photo():
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
        relative_path = os.path.join(project_name, filename)
        data_source.add_photo_to_project(project_name, relative_path)
        socketio.emit('update_project_photos', {"project": project_name, "photos": data_source.get_photos_for_project(project_name)}, broadcast=True)
        return jsonify({"status": "success", "filename": relative_path}), 200
    else:
        return jsonify({"status": "error", "message": "File type not allowed"}), 400

# Endpoint pro synchronizaci a zpracování fotografií
@app.route('/process_photos', methods=['POST'])
def process_photos():
    temp_files = data_source.get_temp_files()
    if not temp_files:
        return jsonify({"status": "success", "message": "No files to process"}), 200
    for file_path in temp_files:
        with open(file_path, 'rb') as f:
            response = requests.post(
                'http://main_program_endpoint/upload',
                files={'file': f}
            )
        if response.status_code == 200:
            os.remove(file_path)
            data_source.remove_temp_file(file_path)
    return jsonify({"status": "success", "processed_files": len(temp_files)}), 200

# SocketIO události
@socketio.on('connect')
def handle_connect():
    logger.info('Nový klient připojen.')
    emit('message', {'data': 'Připojeno k serveru.'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Klient odpojen.')

# Přidání hlavní stránky (/)
@app.route('/')
def home():
    return "Aplikace běží na serveru!"  # Tato stránka bude dostupná na hlavní adrese

# Spuštění serveru
if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000)
    logger.info("API server běží na http://0.0.0.0:5000")
