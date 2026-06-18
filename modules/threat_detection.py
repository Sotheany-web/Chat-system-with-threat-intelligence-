from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import re
import json

from modules.database import get_db

import os


# 1. Rule configure
FAILED_LOGIN_WARNING_LIMIT = 5
FAILED_LOGIN_WARNING_WINDOW = timedelta(minutes=10)

SUSPICIOUS_SUCCESS_FAILED_LIMIT = 5
SUSPICIOUS_SUCCESS_WINDOW = timedelta(minutes=10)

TEMP_LOCK_FAILED_LIMIT = 10
TEMP_LOCK_WINDOW = timedelta(minutes=30)
TEMP_LOCK_DURATION = timedelta(minutes=15)

MESSAGE_LIMIT = 30
MESSAGE_WINDOW = timedelta(minutes=2)

FILE_LIMIT = 8
FILE_WINDOW = timedelta(minutes=5)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".php", ".js", ".jar",
    ".py", ".html", ".css", ".ps1", ".vbs", ".msi"
}

ALLOWED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".docx", ".txt",
    ".xlsx", ".pptx", ".csv", ".zip", ".webp", ".gif",
    ".py", ".html", ".css", ".js", ".php"
}

SQLI_PATTERNS = [
    r"'\s*or\s*1\s*=\s*1",
    r"\bor\s+1\s*=\s*1\b",
    r"--",
    r"/\*",
    r"\*/",
    r"\bunion\s+select\b",
    r"\bdrop\s+table\b",
    r"\binsert\s+into\b",
    r"\bdelete\s+from\b",
]

# 2. Memo
_failed_logins: Dict[str, List[datetime]] = {}
_success_logins: Dict[str, List[datetime]] = {}
_message_logs: Dict[str, List[datetime]] = {}
_file_logs: Dict[str, List[datetime]] = {}
_locked_until: Dict[str, datetime] = {}

# This stores suspicious events for correlation
_user_events: Dict[str, List[dict]] = {}


# Track many actions from the same IP
# _ip_events: Dict[str, List[datetime]] = {}
# _user_ip_history: Dict[str, List[str]] = {}  # ---IPs used by 1 user
# _ip_user_history: Dict[str, List[str]] = {}  # ---Users using SAME IP

CORRELATION_WINDOW = timedelta(minutes=15)


@dataclass
class DetectionResult:
    rule_id: str
    status: str
    severity: str
    action: str
    message: str
    evidence: Dict[str, Any]
    timestamp: str

    def to_dict(self):
        return asdict(self)


def _now():
    return datetime.now()


def _iso(ts: Optional[datetime] = None):
    return (ts or _now()).isoformat(timespec="seconds")


def _clean_old(items: List[datetime], window: timedelta, now: datetime):
    return [t for t in items if now - t <= window]


def log_event(username, event_type, description):
    username = str(username)[:50]
    event_type = str(event_type)[:30]
    description = str(description)[:200]

    conn = get_db()
    cur = conn.cursor()

    try:
        # cur.execute(
        #     "INSERT INTO logs (username, event_type, description) VALUES (?, ?, ?)",
        #     (username, event_type, description)
        # )

        ph = "%s" if os.environ.get("DATABASE_URL") else "?"
        cur.execute(
            f"INSERT INTO logs (username, event_type, description) VALUES ({ph}, {ph}, {ph})",
            (username, event_type, description)
        )

        conn.commit()
        print("LOG SUCCESS:", username, event_type)
    except Exception as e:
        conn.rollback()
        print("Logging failed:", e)
    finally:
        conn.close()


# def _make_result(rule_id, status, severity, message, evidence):
#     result = DetectionResult(
#         rule_id=rule_id,
#         status=status,
#         severity=severity,
#         message=message,
#         evidence=evidence,
#         timestamp=_iso()
#     )

def decide_action(status, severity):
    if status == "OK":
        return "ALLOW"
    if status == "WARNING":
        return "WARN"
    if status == "ALERT" and severity == "MEDIUM":
        return "RATE_LIMIT"
    if status == "ALERT" and severity == "HIGH":
        return "ADMIN_REVIEW"
    if status == "LOCK":
        return "TEMP_LOCK"
    if status == "BLOCK":
        return "BLOCK"
    return "ALLOW"


def _make_result(rule_id, status, severity, message, evidence):
    action = decide_action(status, severity)

    result = DetectionResult(
        rule_id=rule_id,
        status=status,
        severity=severity,
        action=action,
        message=message,
        evidence=evidence,
        timestamp=_iso()
    )

    if status != "OK":
        log_event(
            evidence.get("username", "unknown"),
            rule_id,
            f"{status} | {severity} | {message}"
        )

    return result

# 7 Rules


def check_failed_login(username):
    now = _now()

    if is_account_locked(username):
        return _make_result(
            "R3", "LOCK", "HIGH",
            "Account is temporarily locked.",
            {"username": username}
        )

    _failed_logins.setdefault(username, []).append(now)

    failed_10 = _clean_old(
        _failed_logins[username], FAILED_LOGIN_WARNING_WINDOW, now)
    failed_30 = _clean_old(_failed_logins[username], TEMP_LOCK_WINDOW, now)
    _failed_logins[username] = failed_30

    if len(failed_30) >= TEMP_LOCK_FAILED_LIMIT:
        _locked_until[username] = now + TEMP_LOCK_DURATION
        return _make_result(
            "R3", "LOCK", "HIGH",
            "Too many failed logins. Account locked.",
            {"username": username, "failed_count_30min": len(failed_30)}
        )

    if len(failed_10) >= FAILED_LOGIN_WARNING_LIMIT:
        return _make_result(
            "R1", "WARNING", "MEDIUM",
            "Multiple failed login attempts detected.",
            {"username": username, "failed_count_10min": len(failed_10)}
        )

    return _make_result(
        "R1", "OK", "LOW",
        "Failed login recorded.",
        {"username": username}
    )


def check_successful_login(username):
    now = _now()
    _success_logins.setdefault(username, []).append(now)

    recent_failed = _clean_old(
        _failed_logins.get(username, []),
        SUSPICIOUS_SUCCESS_WINDOW,
        now
    )

    if len(recent_failed) >= SUSPICIOUS_SUCCESS_FAILED_LIMIT:
        return _make_result(
            "R2", "ALERT", "HIGH",
            "Successful login after repeated failures.",
            {"username": username, "failed_before_success": len(recent_failed)}
        )

    return _make_result(
        "R2", "OK", "LOW",
        "Successful login normal.",
        {"username": username}
    )


def is_account_locked(username):
    until = _locked_until.get(username)
    if not until:
        return False
    if _now() >= until:
        _locked_until.pop(username, None)
        return False
    return True


def check_message_rate(username):
    now = _now()
    _message_logs.setdefault(username, []).append(now)
    _message_logs[username] = _clean_old(
        _message_logs[username], MESSAGE_WINDOW, now)

    count = len(_message_logs[username])

    if count >= MESSAGE_LIMIT:
        return _make_result(
            "R4", "ALERT", "MEDIUM",
            "Too many messages in short time.",
            {"username": username, "message_count": count}
        )

    return _make_result(
        "R4", "OK", "LOW",
        "Message rate normal.",
        {"username": username, "message_count": count}
    )


def check_sql_injection(username, input_text, field_name="input"):
    text = input_text or ""

    for pattern in SQLI_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return _make_result(
                "R6", "BLOCK", "HIGH",
                "SQL injection attempt detected.",
                {
                    "username": username,
                    "field_name": field_name,
                    "input_text": text[:200],
                    "pattern": pattern
                }
            )

    return _make_result(
        "R6", "OK", "LOW",
        "No SQL injection detected.",
        {"username": username, "field_name": field_name}
    )

# ----------Messaging SQL---------------


def check_sql_payload_for_chat(username, input_text, field_name="chat_message"):
    text = input_text or ""

    for pattern in SQLI_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return _make_result(
                "R6", "ALERT", "HIGH",
                "Suspicious SQL injection payload detected in chat message.",
                {
                    "username": username,
                    "field_name": field_name,
                    "pattern": pattern
                }
            )

    return _make_result(
        "R6", "OK", "LOW",
        "No SQL injection payload detected in chat message.",
        {"username": username, "field_name": field_name}
    )


def check_file_upload(username, filename, file_size_bytes=0):
    ext = Path(filename).suffix.lower()

    # 1. Empty filename
    if not filename:
        return _make_result(
            "R7", "BLOCK", "HIGH",
            "Missing filename.",
            {"username": username, "filename": filename, "extension": ext}
        )

    # 2. Dangerous extension = block
    # if ext in DANGEROUS_EXTENSIONS:
    #     return _make_result(
    #         "R7", "BLOCK", "HIGH",
    #         "Dangerous file type blocked.",
    #         {"username": username, "filename": filename, "extension": ext}
    #     )

    if ext in DANGEROUS_EXTENSIONS:
        return _make_result(
            "R7", "WARNING", "HIGH",
            "High-risk file type detected.",
            {"username": username, "filename": filename, "extension": ext}
        )

    # 3. Not allowed extension = warning only, not block
    if ext and ext not in ALLOWED_EXTENSIONS:
        return _make_result(
            "R7", "WARNING", "MEDIUM",
            "Uncommon file type detected.",
            {"username": username, "filename": filename, "extension": ext}
        )

    # 4. Count normal uploads
    now = _now()
    _file_logs.setdefault(username, []).append(now)
    _file_logs[username] = _clean_old(_file_logs[username], FILE_WINDOW, now)

    count = len(_file_logs[username])

    if count >= FILE_LIMIT or file_size_bytes > MAX_FILE_SIZE_BYTES:
        return _make_result(
            "R5", "ALERT", "MEDIUM",
            "Abnormal file upload behavior.",
            {
                "username": username,
                "filename": filename,
                "file_count_5min": count,
                "file_size_bytes": file_size_bytes
            }
        )

    return _make_result(
        "R5", "OK", "LOW",
        "File upload normal.",
        {"username": username, "filename": filename, "extension": ext}
    )


# Intelligence Layer
def calculate_risk_score(results):
    score = 0
    reasons = []

    for result in results:
        if result.rule_id == "R1" and result.status == "WARNING":
            score += 20
            reasons.append("Multiple failed login attempts")

        elif result.rule_id == "R2" and result.status == "ALERT":
            score += 40
            reasons.append("Successful login after repeated failures")

        elif result.rule_id == "R3" and result.status == "LOCK":
            score += 70
            reasons.append("Account temporarily locked")

        elif result.rule_id == "R4" and result.status == "ALERT":
            score += 25
            reasons.append("Too many messages sent")

        elif result.rule_id == "R5" and result.status == "ALERT":
            score += 30
            reasons.append("Abnormal file upload behavior")

        elif result.rule_id == "R6" and result.status == "BLOCK":
            score += 80
            reasons.append("SQL injection attempt detected")

        elif result.rule_id == "R7" and result.status in ["WARNING", "ALERT", "BLOCK"]:
            score += 90
            reasons.append("Dangerous file type detected")

    high_rules = ["R2", "R3", "R6", "R7"]

    if any(result.rule_id in high_rules and result.status in ["ALERT", "LOCK", "BLOCK"] for result in results):
        score = max(score, 80)

    # if score >= 120:
    #     level = "HIGH"
    # elif score >= 70:
    #     level = "MEDIUM"
    # elif score >= 30:

    if score >= 80:
        level = "HIGH"
    elif score >= 40:
        level = "MEDIUM"
    elif score >= 1:
        level = "LOW"
    else:
        level = "NORMAL"

    return {
        "risk_score": score,
        "threat_level": level,
        "reasons": reasons
    }


def record_event_for_intelligence(username, result):
    if result.status == "OK":
        return calculate_user_intelligence(username)

    now = _now()

    _user_events.setdefault(username, []).append({
        "rule_id": result.rule_id,
        "status": result.status,
        "severity": result.severity,
        "action": result.action,
        "message": result.message,
        "timestamp": now,
        "evidence": result.evidence
    })

    _user_events[username] = [
        event for event in _user_events[username]
        if now - event["timestamp"] <= CORRELATION_WINDOW
    ]

    return calculate_user_intelligence(username)


def calculate_user_intelligence(username):
    events = _user_events.get(username, [])
    rule_ids = [event["rule_id"] for event in events]

    findings = []
    correlation_score = 0

    if "R1" in rule_ids and "R2" in rule_ids:
        findings.append(
            "Possible account takeover: failed login followed by successful login.")
        correlation_score += 50

    if "R2" in rule_ids and "R7" in rule_ids:
        findings.append(
            "Possible compromised account: suspicious login followed by dangerous file upload.")
        correlation_score += 80

    if "R4" in rule_ids and "R5" in rule_ids:
        findings.append("Possible spam abuse: many messages and many files.")
        correlation_score += 60

    if "R6" in rule_ids and "R1" in rule_ids:
        findings.append(
            "Possible attacker behavior: login attack and SQL injection attempt.")
        correlation_score += 80

    if "R1" in rule_ids and "R2" in rule_ids and "R7" in rule_ids:
        findings.append("High risk account compromise pattern detected.")
        correlation_score += 120

    if "R4" in rule_ids and "R6" in rule_ids:
        findings.append(
            "Possible automated attack: spam behavior combined with SQL injection.")
        correlation_score += 70

    # if "R6" in rule_ids and "R7" in rule_ids:
    #     findings.append(
    #         "Possible malicious payload attempt: SQL injection and dangerous file detected.")
    #     correlation_score += 100

    # if "R4" in rule_ids and "R7" in rule_ids:
    #     findings.append(
    #         "Possible malware spreading: many messages combined with dangerous file upload.")
    #     correlation_score += 90

    # if "R5" in rule_ids and "R7" in rule_ids:
    #     findings.append(
    #         "Possible unsafe file abuse: abnormal file upload behavior and dangerous extension.")
    #     correlation_score += 80

    if "R1" in rule_ids and "R3" in rule_ids:
        findings.append(
            "Possible brute force attack: repeated failed logins caused temporary account lock.")
        correlation_score += 90

    if "R3" in rule_ids and "R6" in rule_ids:
        findings.append(
            "Persistent attacker behavior: account lock pattern combined with SQL injection attempt.")
        correlation_score += 100

    # ------To Save & Restart---------
    if "R4" in rule_ids:
        findings.append("Abnormal message volume detected.")

    if "R5" in rule_ids:
        findings.append("Abnormal file upload activity detected.")

    if "R6" in rule_ids:
        findings.append(
            "Possible SQL injection or suspicious code pattern detected.")

    if "R7" in rule_ids:
        findings.append(
            "High-risk file type detected. File should be reviewed before download.")

    fake_results = []
    for event in events:
        fake_results.append(
            DetectionResult(
                event["rule_id"],
                event["status"],
                event["severity"],
                event.get("action", decide_action(
                    event["status"], event["severity"])),
                event["message"],
                event["evidence"],
                _iso(event["timestamp"])
            )
        )

    risk = calculate_risk_score(fake_results)
    # total_score = risk["risk_score"] + correlation_score
    total_score = min(100, risk["risk_score"] + correlation_score)

    if total_score >= 80:
        level = "HIGH"
    elif total_score >= 40:
        level = "MEDIUM"
    elif total_score >= 1:
        level = "LOW"
    else:
        level = "NORMAL"

    intelligence = {
        "username": username,
        "threat_level": level,
        "risk_score": total_score,
        "reasons": risk["reasons"],
        "correlation_findings": findings,
        "recent_rules": rule_ids
    }

    if level in ["MEDIUM", "HIGH"]:
        log_event(username, "THREAT_INTELLIGENCE",
                  json.dumps(intelligence)[:200])

    return intelligence


# def should_block(result):
#     return result.status in {"BLOCK", "LOCK"}

def should_block(result):
    return result.action in {"BLOCK", "TEMP_LOCK"}


def final_security_decision(result, intelligence, ai_prediction="NORMAL", context="general"):
    score = intelligence.get("risk_score", 0)
    level = intelligence.get("threat_level", "NORMAL")

    # 1. Hard block rules
    if result.action == "TEMP_LOCK":
        return {
            "action": result.action,
            "allow": False,
            "admin_alert": True,
            "user_message": public_message(result)
        }

    # 2. Chat SQL should NOT block, only warn/review
    if context == "chat" and result.rule_id == "R6":
        return {
            "action": "ADMIN_REVIEW",
            "allow": True,
            "admin_alert": True,
            "user_message": "Suspicious code-like message detected. Message allowed but logged."
        }

    # 3. AI says high risk
    if ai_prediction == "HIGH" or level == "HIGH" or score >= 80:
        return {
            "action": "ADMIN_REVIEW",
            "allow": True,
            "admin_alert": True,
            "user_message": "Suspicious activity detected. This action may be reviewed."
        }

    # 4. Medium risk
    if ai_prediction == "MEDIUM" or level == "MEDIUM" or score >= 40:
        return {
            "action": "RATE_LIMIT",
            "allow": True,
            "admin_alert": True,
            "user_message": "Unusual activity detected. Please slow down."
        }

    # 5. Low risk
    if level == "LOW" or score >= 1:
        return {
            "action": "WARN",
            "allow": True,
            "admin_alert": False,
            "user_message": "Warning: unusual activity detected."
        }

    return {
        "action": "ALLOW",
        "allow": True,
        "admin_alert": False,
        "user_message": "OK"
    }

# def public_message(result):
#     if result.status == "LOCK":
#         return "Your account is temporarily locked. Please try again later."
#     if result.status == "BLOCK":
#         return "This action was blocked for security reasons."
#     if result.status == "ALERT":
#         return "Suspicious activity detected. Please slow down."
#     if result.status == "WARNING":
#         return "Warning: unusual activity detected."
#     return "OK"


def response_decision(intelligence):
    score = intelligence.get("risk_score", 0)
    level = intelligence.get("threat_level", "NORMAL")

    if level == "HIGH" or score >= 80:
        return "ADMIN_REVIEW"

    if level == "MEDIUM" or score >= 40:
        return "RATE_LIMIT"

    if level == "LOW" or score >= 1:
        return "WARN"

    return "ALLOW"


def public_message(result):
    if result.action == "TEMP_LOCK":
        return "Your account is temporarily locked. Please try again later."
    if result.action == "BLOCK":
        return "This action was blocked for security reasons."
    if result.action == "RATE_LIMIT":
        return "You are sending too fast. Please slow down."
    if result.action == "ADMIN_REVIEW":
        return "Suspicious activity detected. This action may be reviewed."
    if result.action == "WARN":
        return "Warning: unusual activity detected."
    return "OK"
