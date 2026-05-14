"""
View HeartApp database contents
"""
import sqlite3

conn = sqlite3.connect('heartapp.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 80)
print("USERS TABLE")
print("=" * 80)
try:
    for row in cur.execute("SELECT id, username, name, age, role, created_at FROM users"):
        print(f"ID: {row['id']}, Username: {row['username']}, Name: {row['name']}, Age: {row['age']}, Role: {row['role']}, Created: {row['created_at']}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 80)
print("PREDICTIONS TABLE")
print("=" * 80)
try:
    for row in cur.execute("SELECT id, user_id, age, risk, probability, model_used, created_at FROM predictions"):
        print(f"ID: {row['id']}, User: {row['user_id']}, Age: {row['age']}, Risk: {row['risk']}, Probability: {row['probability']}%, Model: {row['model_used']}, Created: {row['created_at']}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 80)
print("EMERGENCY LOGS TABLE")
print("=" * 80)
try:
    for row in cur.execute("SELECT id, user_id, lat, lng, triggered_at FROM emergency_logs"):
        print(f"ID: {row['id']}, User: {row['user_id']}, Location: ({row['lat']}, {row['lng']}), Triggered: {row['triggered_at']}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 80)
print("DOCTOR NOTES TABLE")
print("=" * 80)
try:
    for row in cur.execute("SELECT id, doctor_id, prediction_id, comment, created_at FROM doctor_notes"):
        print(f"ID: {row['id']}, Doctor: {row['doctor_id']}, Prediction: {row['prediction_id']}, Comment: {row['comment']}, Created: {row['created_at']}")
except Exception as e:
    print(f"Error: {e}")

conn.close()
print("\n" + "=" * 80)
print("Done!")
