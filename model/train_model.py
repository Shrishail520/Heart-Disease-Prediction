"""
Train a Random Forest + Gradient Boosting classifier.
Based on UCI Heart Disease (Cleveland) dataset feature distributions.
Run once: python model/train_model.py
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib, os

SEED = 42
np.random.seed(SEED)
N = 2000  # training samples

def gen_dataset(n):
    rows = []
    for _ in range(n):
        label = np.random.randint(0, 2)
        if label == 1:  # heart disease
            age      = int(np.clip(np.random.normal(58, 10), 29, 80))
            sex      = np.random.choice([0,1], p=[0.20,0.80])
            cp       = np.random.choice([0,1,2,3], p=[0.55,0.15,0.15,0.15])
            trestbps = int(np.clip(np.random.normal(145, 20), 90, 200)) # Increased mean
            chol     = int(np.clip(np.random.normal(270, 55), 130, 600)) # Increased mean
            fbs      = np.random.choice([0,1], p=[0.50,0.50])           # Increased probability
            restecg  = np.random.choice([0,1,2], p=[0.40,0.50,0.10])
            thalach  = int(np.clip(np.random.normal(135, 25), 60, 210))
            exang    = np.random.choice([0,1], p=[0.30,0.70])
            oldpeak  = round(np.clip(np.random.normal(2.2, 1.3), 0, 7.0), 1) # Increased mean
            slope    = np.random.choice([0,1,2], p=[0.15,0.35,0.50])
            ca       = np.random.choice([0,1,2,3], p=[0.25,0.30,0.25,0.20])
            thal     = np.random.choice([1,2,3], p=[0.05,0.20,0.75])
        else:  # no disease
            age      = int(np.clip(np.random.normal(50, 12), 20, 80))
            sex      = np.random.choice([0,1], p=[0.50,0.50])
            cp       = np.random.choice([0,1,2,3], p=[0.10,0.25,0.40,0.25])
            trestbps = int(np.clip(np.random.normal(122, 15), 80, 180)) # Decreased mean
            chol     = int(np.clip(np.random.normal(215, 40), 120, 400)) # Decreased mean
            fbs      = np.random.choice([0,1], p=[0.92, 0.08])          # Decreased probability
            restecg  = np.random.choice([0,1,2], p=[0.60,0.35,0.05])
            thalach  = int(np.clip(np.random.normal(160, 18), 100, 210))
            exang    = np.random.choice([0,1], p=[0.75,0.25])
            oldpeak  = round(np.clip(np.random.normal(0.4, 0.7), 0, 4.0), 1) # Decreased mean
            slope    = np.random.choice([0,1,2], p=[0.10,0.60,0.30])
            ca       = np.random.choice([0,1,2,3], p=[0.75,0.20,0.04,0.01])
            thal     = np.random.choice([1,2,3], p=[0.10,0.75,0.15])
        rows.append([age,sex,cp,trestbps,chol,fbs,restecg,
                     thalach,exang,oldpeak,slope,ca,thal,label])
    cols = ['age','sex','cp','trestbps','chol','fbs','restecg',
            'thalach','exang','oldpeak','slope','ca','thal','target']
    return pd.DataFrame(rows, columns=cols)

df = gen_dataset(N)
FEATURES = ['age','sex','cp','trestbps','chol','fbs','restecg',
            'thalach','exang','oldpeak','slope','ca','thal']
X = df[FEATURES].values
y = df['target'].values

X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=SEED)
scaler = StandardScaler()
X_tr_s = scaler.fit_transform(X_tr)
X_te_s  = scaler.transform(X_te)

rf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=SEED, class_weight='balanced')
rf.fit(X_tr_s, y_tr)

gb = GradientBoostingClassifier(n_estimators=150, learning_rate=0.1, random_state=SEED)
gb.fit(X_tr_s, y_tr)

print(f"RF  accuracy: {accuracy_score(y_te, rf.predict(X_te_s)):.3f}")
print(f"GBM accuracy: {accuracy_score(y_te, gb.predict(X_te_s)):.3f}")
print(classification_report(y_te, rf.predict(X_te_s)))

out = os.path.dirname(os.path.abspath(__file__))
joblib.dump(rf,      os.path.join(out, 'heart_rf.pkl'))
joblib.dump(gb,      os.path.join(out, 'heart_gb.pkl'))
joblib.dump(scaler,  os.path.join(out, 'scaler.pkl'))
joblib.dump(FEATURES,os.path.join(out, 'features.pkl'))
print("Model files saved to", out)
