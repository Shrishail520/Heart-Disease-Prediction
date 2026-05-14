"""
Heart Health Monitoring Application - Flask Backend
Integrates ML model for heart disease prediction with full REST API.
"""
import json
import os
import secrets
import sqlite3
import re

import requests as http_requests
from datetime import datetime
from functools import wraps

import importlib
import joblib
import numpy as np
from flask import Flask, request, jsonify, render_template, session
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

shap = None
try:
    shap_spec = importlib.util.find_spec('shap')
    if shap_spec is not None:
        shap = importlib.import_module('shap')
except Exception as e:
    shap = None
    print(f'WARNING: SHAP import failed: {e}. SHAP explainability is disabled.')

app = Flask(__name__)

IS_PRODUCTION = os.environ.get('FLASK_ENV', '').lower() == 'production'
SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev_secret_key'
if os.environ.get('SECRET_KEY') is None:
    if IS_PRODUCTION:
        raise RuntimeError('SECRET_KEY must be set when FLASK_ENV=production.')
    print('WARNING: SECRET_KEY not set. Using default development secret. Set SECRET_KEY before deployment.')

app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=IS_PRODUCTION
)

bcrypt = Bcrypt(app)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
)
limiter.init_app(app)

# ══════════════════════════════════════════════════
#  LOAD ML MODELS (at startup, once)
# ══════════════════════════════════════════════════
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'model')

try:
    model_rf   = joblib.load(os.path.join(MODEL_DIR, 'heart_rf.pkl'))
    model_gb   = joblib.load(os.path.join(MODEL_DIR, 'heart_gb.pkl'))
    scaler     = joblib.load(os.path.join(MODEL_DIR, 'scaler.pkl'))
    FEATURES   = joblib.load(os.path.join(MODEL_DIR, 'features.pkl'))
    print("ML models loaded successfully")
except Exception as e:
    print(f"WARNING: Could not load models: {e}. Run: python model/train_model.py first.")
    model_rf = model_gb = scaler = None
    FEATURES = ['age','sex','cp','trestbps','chol','fbs','restecg',
                'thalach','exang','oldpeak','slope','ca','thal']

SHAP_EXPLAINER = None
if shap is not None and model_rf is not None:
    try:
        SHAP_EXPLAINER = shap.TreeExplainer(model_rf)
        print('SHAP explainer initialized')
    except Exception as e:
        print(f'WARNING: Could not initialize SHAP explainer: {e}')

# ══════════════════════════════════════════════════
#  DATABASE SETUP
# ══════════════════════════════════════════════════
DB_PATH = os.path.join(os.path.dirname(__file__), 'heartapp.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                password   TEXT NOT NULL,
                name       TEXT NOT NULL,
                age        INTEGER,
                phone      TEXT,
                emergency_contact TEXT,
                role       TEXT NOT NULL DEFAULT 'patient',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS predictions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                age        INTEGER, sex INTEGER, cp INTEGER,
                trestbps   INTEGER, chol INTEGER, fbs INTEGER,
                restecg    INTEGER, thalach INTEGER, exang INTEGER,
                oldpeak    REAL, slope INTEGER, ca INTEGER, thal INTEGER,
                risk       TEXT NOT NULL,
                probability REAL,
                model_used TEXT,
                requested_prescription INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS emergency_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                lat        REAL, lng REAL,
                triggered_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS doctor_notes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id     INTEGER REFERENCES users(id),
                prediction_id INTEGER REFERENCES predictions(id),
                comment       TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );
        """)

        columns = [row['name'] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if 'role' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'patient'")

        columns = [row['name'] for row in conn.execute("PRAGMA table_info(predictions)").fetchall()]
        if 'requested_prescription' not in columns:
            conn.execute("ALTER TABLE predictions ADD COLUMN requested_prescription INTEGER DEFAULT 0")

        conn.commit()

def hash_pw(pw):
    return bcrypt.generate_password_hash(pw).decode('utf-8')


def role_required(role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if session.get('user_role') != role:
                return jsonify({'error': f'{role.title()} access required'}), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return func(*args, **kwargs)
    return wrapper


@app.before_request
def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    if request.method == 'POST':
        token = request.headers.get('X-CSRF-Token')
        if not token or token != session.get('csrf_token'):
            return jsonify({'error': 'CSRF token missing or invalid'}), 403


# ══════════════════════════════════════════════════
#  RISK ANALYSIS HELPER
# ══════════════════════════════════════════════════
def analyse_risk(inputs, probability):
    """Return contributing factors + personalised advice based on inputs."""
    factors = []
    advice  = []

    age = inputs.get('age', 50)
    if age > 60:   factors.append(('Age > 60', 'high'))
    elif age > 50: factors.append(('Age > 50', 'medium'))

    if inputs.get('trestbps', 120) > 140:
        factors.append((f"Blood Pressure {inputs['trestbps']} mmHg", 'high'))
        advice.append('Reduce sodium intake and monitor BP daily.')

    if inputs.get('chol', 200) > 240:
        factors.append((f"Cholesterol {inputs['chol']} mg/dL", 'high'))
        advice.append('Switch to a low-cholesterol diet. Avoid saturated fats.')

    if inputs.get('fbs', 0) == 1:
        factors.append(('Fasting Blood Sugar > 120', 'high'))
        advice.append('Manage blood sugar through diet and medication.')

    if inputs.get('exang', 0) == 1:
        factors.append(('Exercise-induced Angina', 'high'))
        advice.append('Avoid strenuous exercise without cardiologist clearance.')

    cp = inputs.get('cp', 3)
    if cp == 0:
        factors.append(('Typical Angina chest pain', 'high'))
    elif cp == 1:
        factors.append(('Atypical Angina', 'medium'))

    thalach = inputs.get('thalach', 150)
    if thalach < 120:
        factors.append((f'Low Max Heart Rate {thalach} bpm', 'high'))

    if inputs.get('oldpeak', 0) > 2:
        factors.append((f"ST Depression {inputs['oldpeak']}", 'high'))

    if inputs.get('ca', 0) > 0:
        factors.append((f"{inputs['ca']} major vessel(s) narrowed", 'high'))
        advice.append('Consult a cardiologist for vascular assessment.')

    if probability > 0.7:
        advice.append('Schedule a cardiac stress test immediately.')
        advice.append('Carry prescribed medication at all times.')
    elif probability > 0.5:
        advice.append('Schedule a cardiology consultation within 2 weeks.')
        advice.append('Start a supervised cardiac rehabilitation programme.')
    else:
        advice.append('Maintain current healthy lifestyle habits.')
        advice.append('Annual cardiac check-up recommended.')

    return factors, advice

# ══════════════════════════════════════════════════
#  ROUTES - FRONTEND
# ══════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/doctor-login')
def doctor_login():
    return render_template('doctor_login.html')

@app.route('/doctor-register')
def doctor_register():
    return render_template('doctor_register.html')

# ══════════════════════════════════════════════════
#  API - AUTH
# ══════════════════════════════════════════════════
@app.route('/api/register', methods=['POST'])
def register():
    d = request.get_json() or {}
    username = (d.get('username') or '').strip().lower()
    password = d.get('password', '')
    name     = (d.get('name') or '').strip()
    age      = int(d.get('age') or 30)
    phone    = d.get('phone', '')
    emergency_contact = d.get('emergency_contact', '')
    doctor_code = (d.get('doctor_code') or '').strip()

    if not username or not password or not name:
        return jsonify({'error': 'All fields are required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    role = 'patient'
    if doctor_code:
        expected_code = os.environ.get('DOCTOR_REGISTRATION_CODE', 'DOC123')
        if expected_code and doctor_code == expected_code:
            role = 'doctor'
        else:
            return jsonify({'error': 'Invalid doctor registration code'}), 403

    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO users (username,password,name,age,phone,emergency_contact,role) VALUES (?,?,?,?,?,?,?)",
                (username, hash_pw(password), name, age, phone, emergency_contact, role)
            )
            conn.commit()
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already taken'}), 409

    session.permanent = True
    session['user_id'] = uid
    session['user_name'] = name
    session['user_role'] = role
    return jsonify({'id': uid, 'name': name, 'username': username, 'role': role}), 201

@app.route('/api/login', methods=['POST'])
def login():
    d = request.get_json() or {}
    username = (d.get('username') or '').strip().lower()
    password = d.get('password', '')
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()
    if not row or not bcrypt.check_password_hash(row['password'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    session.permanent = True
    session['user_id'] = row['id']
    session['user_name'] = row['name']
    session['user_role'] = row['role']
    return jsonify({'id': row['id'], 'name': row['name'], 'username': row['username'], 'age': row['age'], 'role': row['role']}), 200

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_role', None)
    return jsonify({'ok': True, 'csrf_token': session.get('csrf_token')})

@app.route('/api/me')
def me():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    if 'user_id' not in session:
        return jsonify({'user': None, 'csrf_token': session.get('csrf_token')})
    with get_db() as conn:
        row = conn.execute(
            "SELECT id,name,username,age,phone,emergency_contact,role FROM users WHERE id=?",
            (session['user_id'],)
        ).fetchone()
    return jsonify({'user': dict(row) if row else None, 'csrf_token': session.get('csrf_token')})

# ══════════════════════════════════════════════════
#  API - PREDICTION (core ML endpoint)
# ══════════════════════════════════════════════════
@app.route('/api/predict', methods=['POST'])
def predict():
    if model_rf is None:
        return jsonify({'error': 'ML model not loaded. Run train_model.py first.'}), 503

    d = request.get_json() or {}
    errors = []

    def parse_int(key, low, high, required=True):
        raw = d.get(key)
        if raw is None or raw == '' or (isinstance(raw, str) and raw.strip() == ''):
            if required:
                errors.append(f'{key} is required')
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            errors.append(f'{key} must be an integer')
            return None
        if value < low or value > high:
            errors.append(f'{key} must be between {low} and {high}')
            return None
        return value

    def parse_float(key, low, high):
        raw = d.get(key)
        if raw is None or raw == '' or (isinstance(raw, str) and raw.strip() == ''):
            errors.append(f'{key} is required')
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors.append(f'{key} must be a number')
            return None
        if value < low or value > high:
            errors.append(f'{key} must be between {low} and {high}')
            return None
        return value

    age      = parse_int('age', 20, 90)
    sex      = parse_int('sex', 0, 1)
    cp       = parse_int('cp', 0, 3)
    fbs      = parse_int('fbs', 0, 1)
    restecg  = parse_int('restecg', 0, 2)
    thalach  = parse_int('thalach', 70, 202)
    exang    = parse_int('exang', 0, 1)
    slope    = parse_int('slope', 0, 2)
    ca       = parse_int('ca', 0, 3)
    thal     = parse_int('thal', 1, 3)
    oldpeak  = parse_float('oldpeak', 0.0, 10.0)

    trestbps_raw = d.get('trestbps')
    if trestbps_raw is None or trestbps_raw == '' or (isinstance(trestbps_raw, str) and trestbps_raw.strip() == ''):
        trestbps = 120
        bp_unknown = True
    else:
        trestbps = parse_int('trestbps', 80, 200)
        bp_unknown = False

    chol_raw = d.get('chol')
    if chol_raw is None or chol_raw == '' or (isinstance(chol_raw, str) and chol_raw.strip() == ''):
        chol = 200
        chol_unknown = True
    else:
        chol = parse_int('chol', 100, 600)
        chol_unknown = False

    if errors:
        return jsonify({'errors': errors}), 422

    inputs = {
        'age': age,
        'sex': sex,
        'cp': cp,
        'trestbps': trestbps,
        'chol': chol,
        'fbs': fbs,
        'restecg': restecg,
        'thalach': thalach,
        'exang': exang,
        'oldpeak': oldpeak,
        'slope': slope,
        'ca': ca,
        'thal': thal,
    }

    notes = []
    if bp_unknown:
        notes.append('Using average BP 120 mmHg because your BP is unknown. Get a home BP monitor or pharmacy check for the most accurate result.')
    if chol_unknown:
        notes.append('Using average cholesterol 200 mg/dL because your value is unknown. A lipid profile test will give more accurate risk information.')

    X = np.array([[inputs[f] for f in FEATURES]])
    X_scaled = scaler.transform(X)

    prob = float((model_rf.predict_proba(X_scaled)[0][1] + model_gb.predict_proba(X_scaled)[0][1]) / 2)
    model_name = 'Ensemble (RF + GBM)'
    risk = 'HIGH' if prob >= 0.5 else 'LOW'
    risk_pct = round(prob * 100, 1)
    factors, advice = analyse_risk(inputs, prob)

    shap_values = []
    if SHAP_EXPLAINER is not None:
        try:
            expl = SHAP_EXPLAINER.shap_values(X_scaled)
            expl_arr = expl[1][0] if isinstance(expl, list) else expl[0][0]
            shap_values = [
                {'feature': FEATURES[i], 'shap_value': float(expl_arr[i])}
                for i in range(len(FEATURES))
            ]
        except Exception:
            shap_values = []

    if 'user_id' in session:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO predictions
                (user_id,age,sex,cp,trestbps,chol,fbs,restecg,thalach,exang,oldpeak,slope,ca,thal,risk,probability,model_used)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (session['user_id'], inputs['age'], inputs['sex'], inputs['cp'],
                  inputs['trestbps'], inputs['chol'], inputs['fbs'], inputs['restecg'],
                  inputs['thalach'], inputs['exang'], inputs['oldpeak'], inputs['slope'],
                  inputs['ca'], inputs['thal'], risk, round(prob, 4), model_name))
            conn.commit()

    return jsonify({
        'risk':        risk,
        'probability': risk_pct,
        'model':       model_name,
        'factors':     factors,
        'advice':      advice,
        'notes':       notes,
        'shap':        shap_values,
        'inputs':      inputs,
        'timestamp':   datetime.now().strftime('%d %b %Y, %H:%M')
    })

# ══════════════════════════════════════════════════
#  API - EMERGENCY LOG
# ══════════════════════════════════════════════════
@app.route('/api/emergency', methods=['POST'])
@limiter.limit('6 per hour')
@login_required
def log_emergency():
    """Log emergency activation with location."""
    d   = request.get_json() or {}
    lat = d.get('lat')
    lng = d.get('lng')
    uid = session['user_id']
    with get_db() as conn:
        conn.execute(
            "INSERT INTO emergency_logs (user_id,lat,lng) VALUES (?,?,?)",
            (uid, lat, lng)
        )
        conn.commit()
    return jsonify({'ok': True, 'ambulance': '108', 'message': 'Emergency logged. Calling 108...'})

# ══════════════════════════════════════════════════
#  API - DOCTOR
@app.route('/api/doctor/predictions')
@role_required('doctor')
def doctor_predictions():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT p.id, p.user_id, u.name as patient_name, u.username as patient_username,
                   p.age, p.trestbps, p.chol, p.thalach, p.risk, p.probability, p.model_used,
                   p.requested_prescription,
                   p.created_at,
                   dn.comment as doctor_comment
            FROM predictions p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN (
                SELECT prediction_id, comment
                FROM doctor_notes
                WHERE id IN (SELECT MAX(id) FROM doctor_notes GROUP BY prediction_id)
            ) dn ON dn.prediction_id = p.id
            ORDER BY p.created_at DESC
            LIMIT 100
        """).fetchall()
    return jsonify({'predictions': [dict(r) for r in rows]})

@app.route('/api/doctor/note', methods=['POST'])
@role_required('doctor')
def doctor_note():
    d = request.get_json() or {}
    prediction_id = d.get('prediction_id')
    comment = (d.get('comment') or '').strip()
    if not prediction_id or not comment:
        return jsonify({'error': 'Prediction and comment are required'}), 400
    if len(comment) > 1000:
        return jsonify({'error': 'Comment must be 1000 characters or fewer'}), 400
    try:
        prediction_id = int(prediction_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid prediction'}), 400
    with get_db() as conn:
        prediction = conn.execute(
            "SELECT id FROM predictions WHERE id=?",
            (prediction_id,)
        ).fetchone()
        if prediction is None:
            return jsonify({'error': 'Prediction not found'}), 404
        conn.execute(
            "INSERT INTO doctor_notes (doctor_id,prediction_id,comment) VALUES (?,?,?)",
            (session['user_id'], prediction_id, comment)
        )
        conn.commit()
    return jsonify({'ok': True, 'message': 'Doctor note submitted'})

@app.route('/api/request-prescription', methods=['POST'])
@login_required
def request_prescription():
    d = request.get_json() or {}
    prediction_id = d.get('prediction_id')
    if not prediction_id:
        return jsonify({'error': 'Prediction ID is required'}), 400
    with get_db() as conn:
        # Verify ownership
        row = conn.execute("SELECT id FROM predictions WHERE id=? AND user_id=?", (prediction_id, session['user_id'])).fetchone()
        if not row:
            return jsonify({'error': 'Prediction not found or access denied'}), 404
        conn.execute("UPDATE predictions SET requested_prescription = 1 WHERE id=?", (prediction_id,))
        conn.commit()
    return jsonify({'ok': True, 'message': 'Prescription requested from doctor'})

# ══════════════════════════════════════════════════
#  API - HISTORY
# ══════════════════════════════════════════════════
@app.route('/api/history')
@login_required
def history():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT p.id, p.age, p.trestbps, p.chol, p.thalach, p.risk,
                   p.probability, p.model_used, p.requested_prescription, p.created_at,
                   dn.comment as doctor_comment
            FROM predictions p
            LEFT JOIN (
                SELECT prediction_id, comment
                FROM doctor_notes
                WHERE id IN (SELECT MAX(id) FROM doctor_notes GROUP BY prediction_id)
            ) dn ON dn.prediction_id = p.id
            WHERE p.user_id=?
            ORDER BY p.created_at DESC LIMIT 20
        """, (session['user_id'],)).fetchall()
    return jsonify({'history': [dict(r) for r in rows]})

# ══════════════════════════════════════════════════
#  API - DIET & ROUTINE (static data, easily editable)
# ══════════════════════════════════════════════════
@app.route('/api/diet')
def diet():
    return jsonify({
        'healthy': [
            {'name': 'Oats & Whole Grains', 'benefit': 'Lower LDL cholesterol', 'icon': '🌾'},
            {'name': 'Salmon & Fatty Fish', 'benefit': 'Rich in Omega-3 fatty acids', 'icon': '🐟'},
            {'name': 'Berries & Fruits',    'benefit': 'Antioxidants reduce inflammation', 'icon': '🫐'},
            {'name': 'Leafy Greens',        'benefit': 'Nitrates improve blood pressure', 'icon': '🥬'},
            {'name': 'Walnuts & Almonds',   'benefit': 'Healthy fats protect arteries', 'icon': '🥜'},
            {'name': 'Olive Oil',           'benefit': 'Monounsaturated fats for heart', 'icon': '🫒'},
            {'name': 'Beans & Lentils',     'benefit': 'Fibre lowers blood pressure', 'icon': '🫘'},
            {'name': 'Dark Chocolate (70%+)','benefit': 'Flavonoids improve circulation', 'icon': '🍫'},
        ],
        'avoid': [
            {'name': 'Fried & Fast Food',   'risk': 'Trans fats clog arteries',       'icon': '🍟'},
            {'name': 'Sugary Beverages',    'risk': 'Raises triglycerides',            'icon': '🥤'},
            {'name': 'Processed Meats',     'risk': 'High sodium and saturated fat',   'icon': '🌭'},
            {'name': 'White Bread & Pasta', 'risk': 'Refined carbs spike blood sugar', 'icon': '🍞'},
            {'name': 'Excess Alcohol',      'risk': 'Weakens heart muscle',            'icon': '🍺'},
            {'name': 'High-Salt Snacks',    'risk': 'Raises blood pressure',           'icon': '🧂'},
            {'name': 'Margarine',           'risk': 'Contains harmful trans fats',     'icon': '🧈'},
            {'name': 'Canned Soups',        'risk': 'Extremely high in sodium',        'icon': '🥫'},
        ]
    })

@app.route('/api/routine')
def routine():
    return jsonify({'schedule': [
        {'time': '6:00 AM',  'activity': 'Wake Up & Warm Water',      'detail': 'Drink a glass of warm water with lemon', 'category': 'morning', 'icon': '🌅'},
        {'time': '6:15 AM',  'activity': '15-min Breathing Exercise', 'detail': 'Pranayama / deep breathing to reduce cortisol', 'category': 'exercise', 'icon': '🧘'},
        {'time': '6:30 AM',  'activity': '30-min Brisk Walk',         'detail': 'Low-impact cardio. Keep HR < 70% of max', 'category': 'exercise', 'icon': '🚶'},
        {'time': '7:30 AM',  'activity': 'Heart-Healthy Breakfast',   'detail': 'Oats + fruits + nuts. No salt or sugar added', 'category': 'meal', 'icon': '🥣'},
        {'time': '10:00 AM', 'activity': 'Morning Snack',             'detail': 'A handful of walnuts or a banana', 'category': 'meal', 'icon': '🍌'},
        {'time': '1:00 PM',  'activity': 'Balanced Lunch',            'detail': 'Dal, brown rice, sabzi, salad. Small portions', 'category': 'meal', 'icon': '🍱'},
        {'time': '3:00 PM',  'activity': 'BP & Medication Check',     'detail': 'Take prescribed medicines. Log BP reading', 'category': 'health', 'icon': '💊'},
        {'time': '4:00 PM',  'activity': '20-min Evening Walk',       'detail': 'Gentle walk in park. Avoid heavy exercise', 'category': 'exercise', 'icon': '🌳'},
        {'time': '6:00 PM',  'activity': 'Light Snack',               'detail': 'Fruits or green tea. Avoid caffeine after 4 PM', 'category': 'meal', 'icon': '🍵'},
        {'time': '7:30 PM',  'activity': 'Light Dinner',              'detail': 'Soup, roti, vegetables. Finish by 8 PM', 'category': 'meal', 'icon': '🥗'},
        {'time': '9:00 PM',  'activity': 'Relaxation & Reading',      'detail': 'No screens. Meditate or journal for 15 min', 'category': 'rest', 'icon': '📖'},
        {'time': '10:00 PM', 'activity': 'Sleep',                     'detail': '7-8 hours of quality sleep is essential', 'category': 'rest', 'icon': '😴'},
    ]})

# ══════════════════════════════════════════════════
#  API - EMERGENCY CHAT (Hugging Face)
# ══════════════════════════════════════════════════
HF_API_KEY = os.environ.get('HF_API_KEY', 'YOUR_HF_API_KEY_HERE')
HF_MODEL = 'mistralai/Mistral-7B-Instruct-v0.3'
HF_API_URL = f'https://api-inference.huggingface.co/models/{HF_MODEL}'

@app.route('/api/emergency-chat', methods=['POST'])
@limiter.limit('20 per hour')
def emergency_chat():
    """Send symptom description to Hugging Face LLM and return emergency tips."""
    d = request.get_json() or {}
    user_message = (d.get('message') or '').strip()
    if not user_message:
        return jsonify({'error': 'Please describe your symptoms'}), 400
    if len(user_message) > 1000:
        return jsonify({'error': 'Message too long (max 1000 chars)'}), 400

    system_prompt = (
        "You are an emergency medical assistant integrated into a heart health monitoring app called HeartGuard. "
        "The user is experiencing symptoms and needs immediate guidance. "
        "Provide clear, concise, actionable first-aid tips and advice. "
        "Always remind them to call emergency services (108 in India, or local emergency number) if symptoms are severe. "
        "Focus on cardiac and general emergency guidance. "
        "Keep responses brief (3-5 bullet points), practical, and easy to follow under stress. "
        "IMPORTANT: You are NOT a doctor. Always include a disclaimer that this is not a substitute for professional medical help. "
        "Do NOT diagnose conditions. Only provide general first-aid guidance and recommend seeking professional help."
    )

    prompt = f"<s>[INST] {system_prompt}\n\nUser symptoms: {user_message} [/INST]"

    try:
        hf_response = http_requests.post(
            HF_API_URL,
            headers={
                'Authorization': f'Bearer {HF_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'inputs': prompt,
                'parameters': {
                    'max_new_tokens': 400,
                    'temperature': 0.4,
                    'top_p': 0.9,
                    'do_sample': True,
                    'return_full_text': False
                }
            },
            timeout=30
        )

        if hf_response.status_code == 503:
            return jsonify({
                'reply': '\u23f3 The AI model is currently loading. Please try again in 20-30 seconds.\n\n'
                         '**In the meantime, if this is a serious emergency:**\n'
                         '- \ud83d\udcde Call **108** (Ambulance) immediately\n'
                         '- Stay calm and sit or lie down\n'
                         '- Loosen any tight clothing\n'
                         '- Do not eat or drink anything',
                'status': 'loading'
            })

        if hf_response.status_code != 200:
            return jsonify({
                'reply': '\u26a0\ufe0f Unable to connect to AI assistant right now.\n\n'
                         '**Emergency steps you should follow:**\n'
                         '- \ud83d\udcde Call **108** for an ambulance if you feel severe symptoms\n'
                         '- Sit down and try to stay calm\n'
                         '- Take slow, deep breaths\n'
                         '- Loosen tight clothing around chest and neck\n'
                         '- If prescribed, take your emergency medication\n\n'
                         '*Always seek professional medical help for serious symptoms.*',
                'status': 'fallback'
            })

        result = hf_response.json()
        if isinstance(result, list) and len(result) > 0:
            reply_text = result[0].get('generated_text', '').strip()
        elif isinstance(result, dict):
            reply_text = result.get('generated_text', '').strip()
        else:
            reply_text = ''

        # Clean up the response
        reply_text = re.sub(r'</?s>', '', reply_text)
        reply_text = re.sub(r'\[/?INST\]', '', reply_text)
        reply_text = reply_text.strip()

        if not reply_text:
            reply_text = (
                '\u26a0\ufe0f I could not generate a response. Please try rephrasing your symptoms.\n\n'
                '**If this is an emergency, call 108 immediately.**'
            )

        return jsonify({'reply': reply_text, 'status': 'ok'})

    except http_requests.exceptions.Timeout:
        return jsonify({
            'reply': '\u23f1\ufe0f The request timed out. Please try again.\n\n'
                     '**If this is urgent, call 108 for an ambulance immediately.**',
            'status': 'timeout'
        })
    except Exception as e:
        print(f'Emergency chat error: {e}')
        return jsonify({
            'reply': '\u26a0\ufe0f Something went wrong. Please try again.\n\n'
                     '**For immediate help, call 108 (Ambulance) or 112 (National Emergency).**',
            'status': 'error'
        })

# ══════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    debug = os.environ.get('DEBUG', 'false').lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('PORT', 5000))
    print(f"\n  Heart Health Monitor -> http://localhost:{port}")
    print("  Models: RF + GBM ensemble (84% accuracy)\n")
    app.run(debug=debug, port=port)
