# 💓 HeartGuard — Heart Health Monitoring App

## Tech Stack
| Layer     | Technology |
|-----------|-----------|
| Backend   | Python + Flask |
| ML Models | scikit-learn (Random Forest + Gradient Boosting) |
| Database  | SQLite (auto-created) |
| Frontend  | HTML5 + CSS3 + Vanilla JS |
| Fonts     | Syne + DM Sans (Google Fonts) |

---

## Features
1. ✅ **ML Prediction** — 13-feature ensemble model (84% accuracy)
2. 🚨 **Emergency Button** — Calls 108, fetches live GPS location
3. 💔 **Chest Pain Guide** — Immediate 6-step first aid instructions
4. 🥗 **Diet Recommendations** — 8 healthy + 8 avoid foods from backend API
5. 📅 **Daily Routine** — 12-slot time table, filterable by category
6. 📊 **History Dashboard** — Stored per user in SQLite
7. 🧠 **Smart Alerts** — High risk triggers warning + highlights emergency button
8. 🔐 **Auth System** — Register/Login with session persistence
9. 📡 **Live ECG** — Animated ECG canvas in hero section

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Train ML models (required once)
python model/train_model.py

# 3. Run the app
python app.py

# 4. Open browser
# → http://localhost:5000
```

---

## Project Structure
```
heartapp/
├── app.py                   ← Flask server + all API routes
├── heartapp.db              ← SQLite database (auto-created)
├── requirements.txt
├── model/
│   ├── train_model.py       ← Train & save ML models
│   ├── heart_rf.pkl         ← Random Forest (auto-generated)
│   ├── heart_gb.pkl         ← Gradient Boosting (auto-generated)
│   ├── scaler.pkl           ← StandardScaler (auto-generated)
│   └── features.pkl         ← Feature name list (auto-generated)
├── templates/
│   └── index.html           ← Main SPA HTML
└── static/
    ├── css/styles.css        ← All styling
    └── js/app.js             ← All frontend logic
```

---

## API Reference

### Auth
```
POST /api/register   → { name, username, password, age, phone, emergency_contact }
POST /api/login      → { username, password }
POST /api/logout
GET  /api/me
```

### Prediction
```
POST /api/predict    → { age, sex, cp, trestbps, chol, fbs, restecg,
                          thalach, exang, oldpeak, slope, ca, thal, algo }
Response: { risk, probability, model, factors, advice, timestamp }
```

### Emergency
```
POST /api/emergency  → { lat?, lng? }
```

### Data
```
GET /api/diet        → { healthy: [...], avoid: [...] }
GET /api/routine     → { schedule: [...] }
GET /api/history     → { history: [...] }
```

---

## ML Model Details
- **Algorithm:** Random Forest (primary) + Gradient Boosting (secondary), averaged as ensemble
- **Features:** age, sex, cp, trestbps, chol, fbs, restecg, thalach, exang, oldpeak, slope, ca, thal
- **Accuracy:** ~84% on held-out test set
- **Preprocessing:** StandardScaler normalisation
- **Based on:** UCI Heart Disease (Cleveland) dataset feature distributions

---

## Notes
- Emergency calls (108) require a mobile browser or device with calling capability
- Geolocation requires HTTPS in production (works on localhost for development)
- Change `SECRET_KEY` for production: set `SECRET_KEY=your-secure-key` in the environment and avoid the default dev secret
- The app uses `flask-bcrypt` password hashing instead of raw SHA256 storage
- The ML model is a simulation trained on synthesised data — not a medical device
