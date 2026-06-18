import os

try:
    import joblib
except ImportError:
    joblib = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "threat_model.pkl")

model = None

if joblib:
    try:
        model = joblib.load(MODEL_PATH)
        print("[DEBUG] Threat model loaded successfully.")
    except Exception as e:
        print("[DEBUG] Threat model not found. Using rule-based fallback:", e)
else:
    print("[DEBUG] joblib not installed. Using rule-based fallback.")


def predict_threat(failed_logins, messages, sql_injection, dangerous_file):
    if model:
        prediction = model.predict([[
            failed_logins,
            messages,
            sql_injection,
            dangerous_file
        ]])
        return str(prediction[0])

    # Rule-based fallback if no trained model exists yet
    if sql_injection == 1 or dangerous_file == 1:
        return "HIGH"

    if failed_logins >= 5 or messages >= 30:
        return "MEDIUM"

    return "NORMAL"
