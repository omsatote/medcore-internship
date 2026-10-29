"""
MedCore HMS - a small, dependency-free hospital management application.

Run:
    python index.py
Then open http://127.0.0.1:8000

The application uses SQLite so all created patients, appointments, records,
prescriptions, medicines and invoices survive restarts.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent
DB_PATH = ROOT / "medcore.db"
PORT = int(os.environ.get("PORT", "8765"))
DB_LOCK = threading.Lock()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db() -> None:
    with DB_LOCK, connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                phone TEXT NOT NULL, email TEXT DEFAULT '', dob TEXT DEFAULT '',
                gender TEXT DEFAULT '', blood_group TEXT DEFAULT '',
                allergies TEXT DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
                doctor TEXT NOT NULL, department TEXT NOT NULL, date TEXT NOT NULL,
                time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'CONFIRMED',
                reason TEXT DEFAULT '', created_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
                appointment_id INTEGER, diagnosis TEXT NOT NULL, notes TEXT DEFAULT '',
                vitals TEXT DEFAULT '', treatment TEXT DEFAULT '', created_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
                medicine TEXT NOT NULL, dosage TEXT NOT NULL, frequency TEXT NOT NULL,
                duration TEXT NOT NULL, instructions TEXT DEFAULT '', created_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                category TEXT DEFAULT 'General', stock INTEGER NOT NULL DEFAULT 0,
                reorder_level INTEGER NOT NULL DEFAULT 20, expiry TEXT DEFAULT '',
                unit_price REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
                description TEXT NOT NULL, amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                message TEXT NOT NULL, kind TEXT DEFAULT 'info',
                read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                specialization TEXT NOT NULL, department TEXT NOT NULL,
                phone TEXT DEFAULT '', email TEXT DEFAULT '', available TEXT DEFAULT 'Mon - Fri',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                role TEXT NOT NULL, department TEXT DEFAULT '', phone TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS beds (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ward TEXT NOT NULL,
                bed_number TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'AVAILABLE',
                patient_id INTEGER, created_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS lab_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
                test_name TEXT NOT NULL, result TEXT DEFAULT '', reference_range TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ORDERED', ordered_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patients(id)
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
                entity TEXT NOT NULL, entity_id INTEGER, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hospital_settings (
                id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL,
                address TEXT DEFAULT '', phone TEXT DEFAULT '', currency TEXT DEFAULT 'INR'
            );
            """
        )
        if db.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0:
            db.execute(
                "INSERT INTO patients(name,phone,email,dob,gender,blood_group,allergies,created_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Aarav Sharma", "+91 98765 43210", "aarav@example.com", "1991-04-12", "Male", "O+", "Penicillin", now()),
            )
            db.execute(
                "INSERT INTO patients(name,phone,email,dob,gender,blood_group,allergies,created_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Meera Iyer", "+91 99887 66554", "meera@example.com", "1987-09-22", "Female", "B+", "None known", now()),
            )
        if db.execute("SELECT COUNT(*) FROM medicines").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO medicines(name,category,stock,reorder_level,expiry,unit_price) VALUES(?,?,?,?,?,?)",
                [
                    ("Amoxicillin 500mg", "Antibiotic", 84, 20, "2027-02-14", 12.5),
                    ("Paracetamol 650mg", "Analgesic", 210, 40, "2027-08-30", 3.0),
                    ("Metformin 500mg", "Diabetes", 18, 30, "2026-12-05", 8.0),
                ],
            )
        if db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0:
            db.execute(
                "INSERT INTO notifications(title,message,kind,created_at) VALUES(?,?,?,?)",
                ("Welcome to MedCore", "Your hospital workspace is ready.", "success", now()),
            )
        if db.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO doctors(name,specialization,department,phone,email,available,created_at) VALUES(?,?,?,?,?,?,?)",
                [
                    ("Dr. Ananya Rao", "Internal Medicine", "General Medicine", "+91 98765 10001", "ananya@medcore.com", "Mon - Fri, 09:00 - 17:00", now()),
                    ("Dr. Vikram Mehta", "Cardiology", "Cardiology", "+91 98765 10002", "vikram@medcore.com", "Tue - Sat, 10:00 - 18:00", now()),
                    ("Dr. Kavya Nair", "Pediatrics", "Pediatrics", "+91 98765 10003", "kavya@medcore.com", "Mon - Thu, 09:00 - 15:00", now()),
                ],
            )
        if db.execute("SELECT COUNT(*) FROM staff").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO staff(name,role,department,phone,status,created_at) VALUES(?,?,?,?,?,?)",
                [
                    ("Riya Kapoor", "Senior Nurse", "General Medicine", "+91 98765 20001", "ACTIVE", now()),
                    ("Arjun Singh", "Lab Technician", "Laboratory", "+91 98765 20002", "ACTIVE", now()),
                    ("Neha Joshi", "Receptionist", "Front Office", "+91 98765 20003", "ACTIVE", now()),
                ],
            )
        if db.execute("SELECT COUNT(*) FROM beds").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO beds(ward,bed_number,status,created_at) VALUES(?,?,?,?)",
                [("General Ward", "G-101", "OCCUPIED", now()), ("General Ward", "G-102", "AVAILABLE", now()), ("ICU", "ICU-01", "OCCUPIED", now()), ("Pediatrics", "P-201", "AVAILABLE", now())],
            )
        if db.execute("SELECT COUNT(*) FROM hospital_settings").fetchone()[0] == 0:
            db.execute("INSERT INTO hospital_settings(id,name,address,phone) VALUES(1,?,?,?)", ("MedCore City Hospital", "24 Sunrise Avenue, Bengaluru", "+91 80 4000 2200"))


def response(data=None, message="OK", status=HTTPStatus.OK, meta=None):
    body = {"success": status < 400, "data": data, "message": message}
    if meta is not None:
        body["meta"] = meta
    return status, body


def validate(payload, required):
    missing = [field for field in required if not str(payload.get(field, "")).strip()]
    if missing:
        return "Required fields: " + ", ".join(missing)
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "MedCore/1.0"

    def log_message(self, fmt, *args):
        return

    def send_json(self, status, body):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_file(self):
        requested = urlparse(self.path).path.lstrip("/")
        path = ROOT / ("index.html" if requested in ("", "index.html") else requested)
        if path.name == "index.html" and requested not in ("", "index.html"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if path.parent != ROOT or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 1_000_000:
            raise ValueError("Request body is too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            return self.send_file()
        if not parsed.path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            status, body = self.api_get(parsed.path[5:], parse_qs(parsed.query))
            self.send_json(status, body)
        except Exception as exc:
            self.send_json(500, response(None, str(exc), 500)[1])

    def do_POST(self):
        if not self.path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            status, body = self.api_post(self.path[5:], self.read_body())
            self.send_json(status, body)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, response(None, str(exc), 400)[1])
        except Exception as exc:
            self.send_json(500, response(None, str(exc), 500)[1])

    def do_PATCH(self):
        if not self.path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            status, body = self.api_patch(self.path[5:], self.read_body())
            self.send_json(status, body)
        except Exception as exc:
            self.send_json(500, response(None, str(exc), 500)[1])

    def api_get(self, route, query):
        with connect() as db:
            if route == "summary":
                total = db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
                today = datetime.now().strftime("%Y-%m-%d")
                appts = db.execute("SELECT COUNT(*) FROM appointments WHERE date LIKE ?", (today + "%",)).fetchone()[0]
                revenue = db.execute("SELECT COALESCE(SUM(amount),0) FROM invoices WHERE status='PAID'").fetchone()[0]
                pending = db.execute("SELECT COUNT(*) FROM invoices WHERE status='PENDING'").fetchone()[0]
                doctors = db.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
                staff = db.execute("SELECT COUNT(*) FROM staff WHERE status='ACTIVE'").fetchone()[0]
                beds = db.execute("SELECT COUNT(*) FROM beds").fetchone()[0]
                occupied = db.execute("SELECT COUNT(*) FROM beds WHERE status='OCCUPIED'").fetchone()[0]
                return response({"patients": total, "doctors": doctors, "staff": staff, "appointments_today": appts, "revenue": revenue, "pending_invoices": pending, "beds": beds, "occupied_beds": occupied})
            if route in ("patients", "appointments", "records", "prescriptions", "medicines", "invoices", "notifications", "doctors", "staff", "beds", "lab_orders", "audit_logs", "hospital_settings"):
                table = route
                where = ""
                args = []
                if route == "patients" and query.get("search"):
                    term = "%" + query["search"][0] + "%"
                    where = "WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?"
                    args = [term, term, term]
                rows = [dict(row) for row in db.execute(f"SELECT * FROM {table} {where} ORDER BY id DESC", args).fetchall()]
                return response(rows, meta={"total": len(rows), "page": 1, "limit": 100, "totalPages": 1})
            if route == "analytics":
                return response({
                    "appointments_by_status": [dict(row) for row in db.execute("SELECT status,COUNT(*) AS total FROM appointments GROUP BY status").fetchall()],
                    "revenue_by_status": [dict(row) for row in db.execute("SELECT status,COALESCE(SUM(amount),0) AS total FROM invoices GROUP BY status").fetchall()],
                    "patients_by_month": [dict(row) for row in db.execute("SELECT substr(created_at,1,7) AS month,COUNT(*) AS total FROM patients GROUP BY month ORDER BY month").fetchall()],
                })
            return response(None, "Endpoint not found", 404)

    def api_post(self, route, payload):
        required = {
            "login": ["email", "password"],
            "patients": ["name", "phone"],
            "appointments": ["patient_id", "doctor", "department", "date", "time"],
            "records": ["patient_id", "diagnosis"],
            "prescriptions": ["patient_id", "medicine", "dosage", "frequency", "duration"],
            "invoices": ["patient_id", "description", "amount"],
            "doctors": ["name", "specialization", "department"],
            "staff": ["name", "role"],
            "beds": ["ward", "bed_number"],
            "lab_orders": ["patient_id", "test_name"],
        }
        error = validate(payload, required.get(route, []))
        if error:
            return response(None, error, 400)
        with DB_LOCK, connect() as db:
            if route == "login":
                # Demo login is intentionally visible in the UI; production should use bcrypt/JWT.
                if payload["email"].lower() != "admin@medcore.com" or payload["password"] != "medcore123":
                    return response(None, "Invalid email or password", 401)
                return response({"user": {"name": "Dr. Ananya Rao", "role": "Hospital Admin", "email": payload["email"]}, "token": secrets.token_urlsafe(24)}, "Signed in")
            table = route
            fields = {
                "patients": ["name", "phone", "email", "dob", "gender", "blood_group", "allergies"],
                "appointments": ["patient_id", "doctor", "department", "date", "time", "reason"],
                "records": ["patient_id", "appointment_id", "diagnosis", "notes", "vitals", "treatment"],
                "prescriptions": ["patient_id", "medicine", "dosage", "frequency", "duration", "instructions"],
                "invoices": ["patient_id", "description", "amount"],
                "doctors": ["name", "specialization", "department", "phone", "email", "available"],
                "staff": ["name", "role", "department", "phone", "status"],
                "beds": ["ward", "bed_number", "status", "patient_id"],
                "lab_orders": ["patient_id", "test_name", "result", "reference_range", "status"],
            }.get(table)
            if not fields:
                return response(None, "Endpoint not found", 404)
            if table == "appointments":
                conflict = db.execute(
                    "SELECT 1 FROM appointments WHERE doctor=? AND date=? AND time=? AND status NOT IN ('CANCELLED','NO_SHOW')",
                    (payload["doctor"], payload["date"], payload["time"]),
                ).fetchone()
                if conflict:
                    return response(None, "This doctor is already booked for that time slot.", 409)
            values = [payload.get(field, "") for field in fields]
            timestamp_field = "ordered_at" if table == "lab_orders" else "created_at"
            cursor = db.execute(
                f"INSERT INTO {table} ({','.join(fields)},{timestamp_field}) VALUES ({','.join('?' for _ in fields)},?)",
                values + [now()],
            )
            item = dict(db.execute(f"SELECT * FROM {table} WHERE id=?", (cursor.lastrowid,)).fetchone())
            title = {"patients": "Patient registered", "appointments": "Appointment booked", "records": "Medical record saved", "prescriptions": "Prescription issued", "invoices": "Invoice created", "doctors": "Doctor added", "staff": "Staff member added", "beds": "Bed updated", "lab_orders": "Lab order created"}[table]
            db.execute("INSERT INTO notifications(title,message,kind,created_at) VALUES(?,?,?,?)", (title, f"{title} successfully.", "success", now()))
            db.execute("INSERT INTO audit_logs(action,entity,entity_id,created_at) VALUES(?,?,?,?)", ("CREATE", table, cursor.lastrowid, now()))
            return response(item, title, 201)

    def api_patch(self, route, payload):
        parts = route.split("/")
        if len(parts) != 2 or parts[0] not in {"appointments", "invoices"}:
            return response(None, "Endpoint not found", 404)
        record_id = parts[1]
        status = payload.get("status", "").upper()
        allowed = {"PENDING", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "NO_SHOW"} if parts[0] == "appointments" else {"PENDING", "PAID", "CANCELLED"}
        if status not in allowed:
            return response(None, "Invalid appointment status", 400)
        with DB_LOCK, connect() as db:
            cursor = db.execute(f"UPDATE {parts[0]} SET status=? WHERE id=?", (status, record_id))
            if cursor.rowcount == 0:
                return response(None, f"{parts[0].replace('_', ' ').title()} not found", 404)
            db.execute("INSERT INTO audit_logs(action,entity,entity_id,created_at) VALUES(?,?,?,?)", ("UPDATE", parts[0], record_id, now()))
            return response(dict(db.execute(f"SELECT * FROM {parts[0]} WHERE id=?", (record_id,)).fetchone()), f"{parts[0].replace('_', ' ').title()} updated")


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MedCore HMS | Hospital workspace</title>
<style>
:root{--ink:#17202a;--muted:#6b7280;--yellow:#f6c844;--yellow-soft:#fff7d6;--line:#ece8dc;--green:#16805b;--red:#c84343;--cream:#fffdf6}
.login-screen{min-height:100vh;display:grid;place-items:center;background:var(--cream);padding:20px}.login-screen.hidden{display:none}.login-card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:34px;width:min(420px,100%);box-shadow:0 18px 50px #17202a12}.login-card h1{margin:28px 0 6px;font-size:28px}.login-form{display:grid;gap:15px;margin-top:24px}.login-form label{display:grid;gap:7px;color:var(--muted);font-size:12px}.login-form input{border:1px solid var(--line);border-radius:8px;padding:12px;font:inherit}.login-form .primary{font-size:14px;margin-top:4px}.login-error{color:var(--red);font-size:12px;min-height:16px;margin:0}.demo-hint{color:var(--muted);font-size:12px;margin:22px 0 0}.app{display:none}.app.visible{display:flex}.logout{margin-left:auto;border:0;background:transparent;color:var(--muted);font:inherit;font-size:12px;cursor:pointer}.logout:hover{color:var(--red)}
*{box-sizing:border-box}body{margin:0;background:var(--cream);color:var(--ink);font:14px Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
.app{display:flex;min-height:100vh}.side{width:240px;background:#fff;border-right:1px solid var(--line);padding:24px 16px;position:fixed;inset:0 auto 0 0}.brand{display:flex;gap:10px;align-items:center;font-size:19px;font-weight:800;margin:0 10px 28px}.mark{background:var(--yellow);border-radius:11px;width:35px;height:35px;display:grid;place-items:center;font-weight:900}.nav{display:grid;gap:5px}.nav button{background:transparent;border:0;text-align:left;padding:12px 13px;border-radius:10px;color:#66707a;cursor:pointer;font:inherit}.nav button:hover,.nav button.active{background:var(--yellow-soft);color:var(--ink);font-weight:700}.nav button.active{box-shadow:inset 3px 0 var(--yellow)}.user{position:absolute;bottom:22px;border-top:1px solid var(--line);padding:18px 10px;width:calc(100% - 32px);display:flex;gap:9px;align-items:center}.avatar{background:#e8f4ec;color:var(--green);font-weight:800;border-radius:50%;width:32px;height:32px;display:grid;place-items:center}.main{margin-left:240px;width:calc(100% - 240px);padding:26px 34px 50px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px}.eyebrow{font-size:12px;color:var(--muted);margin:0 0 5px}.title{font-size:27px;margin:0;font-weight:800}.top-actions{display:flex;gap:10px;align-items:center}.bell{border:1px solid var(--line);background:#fff;border-radius:9px;padding:10px 13px;cursor:pointer}.primary{background:var(--yellow);border:0;border-radius:9px;padding:11px 16px;font-weight:750;cursor:pointer;color:var(--ink)}.primary:hover{background:#eebd2b}.ghost{background:#fff;border:1px solid var(--line);border-radius:9px;padding:10px 14px;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:19px}.metric{font-size:27px;font-weight:800;margin:7px 0}.label{color:var(--muted);font-size:12px}.trend{color:var(--green);font-size:12px}.section{margin-top:24px}.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}.section-head h2{font-size:17px;margin:0}.content-grid{display:grid;grid-template-columns:1.55fr 1fr;gap:18px}.table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse}.table th{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--line);padding:11px 8px}.table td{padding:14px 8px;border-bottom:1px solid #f1eee8}.table tr:last-child td{border-bottom:0}.badge{display:inline-block;border-radius:20px;padding:5px 9px;font-size:11px;font-weight:700;background:var(--yellow-soft)}.badge.green{background:#e7f6ed;color:var(--green)}.badge.red{background:#fceaea;color:var(--red)}.quick{display:grid;grid-template-columns:1fr 1fr;gap:10px}.quick button{padding:16px;text-align:left;background:#fff;border:1px solid var(--line);border-radius:11px;cursor:pointer}.quick strong{display:block;margin-bottom:4px}.quick span{color:var(--muted);font-size:12px}.page{display:none}.page.active{display:block}.toolbar{display:flex;gap:10px;margin-bottom:15px}.search{flex:1;padding:11px 13px;border:1px solid var(--line);border-radius:9px;background:#fff;font:inherit}.form{display:grid;grid-template-columns:1fr 1fr;gap:12px}.form label{font-size:12px;color:var(--muted);display:grid;gap:6px}.form input,.form select,.form textarea{border:1px solid var(--line);border-radius:8px;padding:10px;font:inherit;background:#fff}.form textarea{min-height:75px;resize:vertical}.full{grid-column:1/-1}.modal{position:fixed;inset:0;background:#17202a66;display:none;place-items:center;padding:20px;z-index:5}.modal.open{display:grid}.modal-card{background:#fff;border-radius:16px;max-width:620px;width:100%;padding:24px;max-height:90vh;overflow:auto}.modal-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.modal-head h2{margin:0}.close{border:0;background:transparent;font-size:24px;cursor:pointer}.toast{position:fixed;right:25px;bottom:25px;background:#17202a;color:#fff;border-radius:10px;padding:13px 17px;display:none;z-index:10}.toast.show{display:block}.empty{padding:32px;text-align:center;color:var(--muted)}@media(max-width:850px){.side{width:70px;padding:18px 8px}.brand span,.nav button span,.user div:not(.avatar){display:none}.brand{margin:0 9px 28px}.main{margin-left:70px;width:calc(100% - 70px);padding:22px 18px}.grid{grid-template-columns:repeat(2,1fr)}.content-grid{grid-template-columns:1fr}.top{align-items:flex-start}.title{font-size:22px}}@media(max-width:520px){.grid,.form{grid-template-columns:1fr}.full{grid-column:auto}.main{padding:18px 12px}.top-actions .primary{display:none}}
</style></head>
<body><section class="login-screen" id="login-screen"><div class="login-card"><div class="brand"><div class="mark">+</div><span>MedCore</span></div><h1>Welcome back</h1><p class="label">Sign in to your hospital workspace</p><form id="login-form" class="login-form"><label>Email address<input name="email" type="email" value="admin@medcore.com" required></label><label>Password<input name="password" type="password" placeholder="Enter your password" required></label><button class="primary" type="submit">Sign in</button><p class="login-error" id="login-error"></p></form><p class="demo-hint">Demo: admin@medcore.com / medcore123</p></div></section><div class="app" id="app"><aside class="side"><div class="brand"><div class="mark">+</div><span>MedCore</span></div>
<nav class="nav"><button class="active" data-page="dashboard">◈ <span>Overview</span></button><button data-page="patients">♙ <span>Patients</span></button><button data-page="appointments">◷ <span>Appointments</span></button><button data-page="records">▣ <span>Medical records</span></button><button data-page="pharmacy">⌁ <span>Pharmacy</span></button><button data-page="billing">₹ <span>Billing</span></button></nav>
<div class="user"><div class="avatar">AR</div><div><strong>Ananya Rao</strong><small style="display:block;color:var(--muted)">Hospital Admin</small></div><button class="logout" onclick="logout()">Log out</button></div></aside>
<main class="main"><div class="top"><div><p class="eyebrow">Thursday, 29 October 2026</p><h1 class="title" id="page-title">Good morning, Ananya</h1></div><div class="top-actions"><button class="bell" onclick="showNotifications()">♧ <span id="notice-count">1</span></button><button class="primary" onclick="openModal('patient')">+ New patient</button></div></div>
<section class="page active" id="dashboard"><div class="grid" id="metrics"></div><div class="content-grid section"><div class="card"><div class="section-head"><h2>Today's appointments</h2><button class="ghost" onclick="go('appointments')">View all</button></div><div class="table-wrap"><table class="table"><thead><tr><th>Time</th><th>Patient</th><th>Doctor</th><th>Status</th></tr></thead><tbody id="dash-appts"></tbody></table></div></div><div class="card"><div class="section-head"><h2>Quick actions</h2></div><div class="quick"><button onclick="openModal('patient')"><strong>Register patient</strong><span>Create a new profile</span></button><button onclick="openModal('appointment')"><strong>Book appointment</strong><span>Find a time slot</span></button><button onclick="openModal('record')"><strong>Add medical record</strong><span>Document an encounter</span></button><button onclick="openModal('invoice')"><strong>Create invoice</strong><span>Charge for a service</span></button></div></div></div><div class="card section"><div class="section-head"><h2>Recent activity</h2></div><div id="activity"></div></div></section>
<section class="page" id="patients"><div class="toolbar"><input class="search" id="patient-search" placeholder="Search by name, phone or email..." oninput="loadPatients()"><button class="primary" onclick="openModal('patient')">+ Register patient</button></div><div class="card"><table class="table"><thead><tr><th>Patient</th><th>Contact</th><th>Date of birth</th><th>Blood group</th><th>Allergies</th></tr></thead><tbody id="patients-list"></tbody></table></div></section>
<section class="page" id="appointments"><div class="toolbar"><button class="primary" onclick="openModal('appointment')">+ Book appointment</button><button class="ghost" onclick="loadAppointments()">↻ Refresh</button></div><div class="card"><table class="table"><thead><tr><th>Date / time</th><th>Patient</th><th>Doctor</th><th>Department</th><th>Status</th><th>Update</th></tr></thead><tbody id="appointments-list"></tbody></table></div></section>
<section class="page" id="records"><div class="toolbar"><button class="primary" onclick="openModal('record')">+ Add medical record</button></div><div class="card"><table class="table"><thead><tr><th>Created</th><th>Patient</th><th>Diagnosis</th><th>Vitals</th><th>Treatment</th></tr></thead><tbody id="records-list"></tbody></table></div></section>
<section class="page" id="pharmacy"><div class="card"><div class="section-head"><h2>Medicine inventory</h2><span class="label">FIFO stock monitoring</span></div><table class="table"><thead><tr><th>Medicine</th><th>Category</th><th>Available</th><th>Expiry</th><th>Unit price</th></tr></thead><tbody id="medicines-list"></tbody></table></div></section>
<section class="page" id="billing"><div class="toolbar"><button class="primary" onclick="openModal('invoice')">+ Create invoice</button></div><div class="card"><table class="table"><thead><tr><th>Invoice</th><th>Patient</th><th>Description</th><th>Amount</th><th>Status</th><th>Action</th></tr></thead><tbody id="invoices-list"></tbody></table></div></section>
</main></div><div class="toast" id="toast"></div><div class="modal" id="modal"><div class="modal-card"><div class="modal-head"><h2 id="modal-title"></h2><button class="close" onclick="closeModal()">×</button></div><form class="form" id="modal-form"></form></div></div>
<script>
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s); let patients=[];
async function api(path, options={}){const r=await fetch('/api/'+path,{headers:{'Content-Type':'application/json'},...options});const j=await r.json();if(!j.success)throw Error(j.message||j.error?.message||'Request failed');return j}
function showApp(){ $('#login-screen').classList.add('hidden'); $('#app').classList.add('visible'); loadDashboard() }
function logout(){ localStorage.removeItem('medcore-user'); $('#app').classList.remove('visible'); $('#login-screen').classList.remove('hidden'); $('#login-form').reset(); $('#login-error').textContent='' }
$('#login-form').onsubmit=async e=>{e.preventDefault();const form=e.target;const error=$('#login-error');error.textContent='';try{const result=await api('login',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});localStorage.setItem('medcore-user',JSON.stringify(result.data.user));showApp()}catch(err){error.textContent=err.message}}
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2800)}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function badge(v){const c=['COMPLETED','CONFIRMED','PAID'].includes(v)?'green':['CANCELLED','NO_SHOW'].includes(v)?'red':'';return `<span class="badge ${c}">${esc(v)}</span>`}
function go(page){$$('.page').forEach(x=>x.classList.toggle('active',x.id===page));$$('.nav button').forEach(x=>x.classList.toggle('active',x.dataset.page===page));$('#page-title').textContent=page==='dashboard'?'Good morning, Ananya':page[0].toUpperCase()+page.slice(1);({patients:loadPatients,appointments:loadAppointments,records:loadRecords,pharmacy:loadMedicines,billing:loadInvoices}[page]||loadDashboard)()}
$$('.nav button').forEach(b=>b.onclick=()=>go(b.dataset.page));
async function loadDashboard(){try{const [s,a,n]=await Promise.all([api('summary'),api('appointments'),api('notifications')]);$('#metrics').innerHTML=`<div class="card"><span class="label">Total patients</span><div class="metric">${s.data.patients}</div><span class="trend">↑ 12% this month</span></div><div class="card"><span class="label">Appointments today</span><div class="metric">${s.data.appointments_today}</div><span class="trend">Live schedule</span></div><div class="card"><span class="label">Collected revenue</span><div class="metric">₹${Number(s.data.revenue).toLocaleString()}</div><span class="trend">↑ 8.4% this month</span></div><div class="card"><span class="label">Pending invoices</span><div class="metric">${s.data.pending_invoices}</div><span class="trend">Needs attention</span></div>`;$('#dash-appts').innerHTML=a.data.slice(0,5).map(x=>`<tr><td><strong>${esc(x.time)}</strong><br><span class="label">${esc(x.date)}</span></td><td>Patient #${x.patient_id}</td><td>${esc(x.doctor)}</td><td>${badge(x.status)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No appointments yet</td></tr>';$('#activity').innerHTML=n.data.slice(0,4).map(x=>`<p><span class="badge green">NEW</span> &nbsp;<strong>${esc(x.title)}</strong> — ${esc(x.message)} <span class="label">${esc(x.created_at)}</span></p>`).join('')}catch(e){toast(e.message)}}
async function loadPatients(){const q=$('#patient-search')?.value||'';const r=await api('patients'+(q?'?search='+encodeURIComponent(q):''));patients=r.data;$('#patients-list').innerHTML=patients.map(x=>`<tr><td><strong>${esc(x.name)}</strong><br><span class="label">ID MC-${String(x.id).padStart(4,'0')}</span></td><td>${esc(x.phone)}<br><span class="label">${esc(x.email)}</span></td><td>${esc(x.dob)||'—'}</td><td>${esc(x.blood_group)||'—'}</td><td>${esc(x.allergies)||'None known'}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">No patients found</td></tr>'}
async function loadAppointments(){const r=await api('appointments');$('#appointments-list').innerHTML=r.data.map(x=>`<tr><td><strong>${esc(x.date)}</strong><br>${esc(x.time)}</td><td>Patient #${x.patient_id}</td><td>${esc(x.doctor)}</td><td>${esc(x.department)}</td><td>${badge(x.status)}</td><td><select onchange="updateAppointment(${x.id},this.value)" style="padding:6px;border:1px solid var(--line);border-radius:6px"><option>${esc(x.status)}</option><option>CONFIRMED</option><option>IN_PROGRESS</option><option>COMPLETED</option><option>CANCELLED</option></select></td></tr>`).join('')||'<tr><td colspan="6" class="empty">No appointments found</td></tr>'}
async function updateAppointment(id,status){try{await api('appointments/'+id,{method:'PATCH',body:JSON.stringify({status})});toast('Appointment updated');loadAppointments()}catch(e){toast(e.message)}}
async function loadRecords(){const r=await api('records');$('#records-list').innerHTML=r.data.map(x=>`<tr><td>${esc(x.created_at)}</td><td>Patient #${x.patient_id}</td><td><strong>${esc(x.diagnosis)}</strong><br><span class="label">${esc(x.notes)}</span></td><td>${esc(x.vitals)||'—'}</td><td>${esc(x.treatment)||'—'}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">No medical records yet</td></tr>'}
async function loadMedicines(){const r=await api('medicines');$('#medicines-list').innerHTML=r.data.map(x=>`<tr><td><strong>${esc(x.name)}</strong></td><td>${esc(x.category)}</td><td>${x.stock<=x.reorder_level?'<span class="badge red">':''}${x.stock}${x.stock<=x.reorder_level?'</span>':''}</td><td>${esc(x.expiry)}</td><td>₹${Number(x.unit_price).toFixed(2)}</td></tr>`).join('')}
async function loadInvoices(){const r=await api('invoices');$('#invoices-list').innerHTML=r.data.map(x=>`<tr><td><strong>INV-${String(x.id).padStart(4,'0')}</strong><br><span class="label">${esc(x.created_at)}</span></td><td>Patient #${x.patient_id}</td><td>${esc(x.description)}</td><td><strong>₹${Number(x.amount).toLocaleString()}</strong></td><td>${badge(x.status)}</td><td><button class="ghost" onclick="toast('Payment gateway ready for integration')">Collect</button></td></tr>`).join('')||'<tr><td colspan="6" class="empty">No invoices found</td></tr>'}
function openModal(type){const configs={patient:{title:'Register new patient',fields:[['name','Full name','text'],['phone','Phone number','tel'],['email','Email address','email'],['dob','Date of birth','date'],['gender','Gender','text'],['blood_group','Blood group','text'],['allergies','Allergies','text']]},appointment:{title:'Book appointment',fields:[['patient_id','Patient ID','number'],['doctor','Doctor','text'],['department','Department','text'],['date','Date','date'],['time','Time','time'],['reason','Reason for visit','text']]},record:{title:'Add medical record',fields:[['patient_id','Patient ID','number'],['diagnosis','Diagnosis','text'],['vitals','Vitals (BP, pulse, temperature)','text'],['notes','Clinical notes','textarea'],['treatment','Treatment plan','textarea']]},invoice:{title:'Create invoice',fields:[['patient_id','Patient ID','number'],['description','Service description','text'],['amount','Amount (₹)','number']]}};const requiredFields={patient:['name','phone'],appointment:['patient_id','doctor','department','date','time'],record:['patient_id','diagnosis'],invoice:['patient_id','description','amount']}[type]||[];const c=configs[type];$('#modal-title').textContent=c.title;$('#modal-form').dataset.type=type;$('#modal-form').innerHTML=c.fields.map(([n,l,t])=>`<label class="${t==='textarea'?'full':''}">${l}<${t==='textarea'?'textarea':'input'} name="${n}" ${t!=='textarea'?`type="${t}"`:''} ${requiredFields.includes(n)?'required':''}></${t==='textarea'?'textarea':'input'}></label>`).join('')+'<div class="full" style="display:flex;justify-content:flex-end;gap:8px"><button type="button" class="ghost" onclick="closeModal()">Cancel</button><button class="primary">Save</button></div>';$('#modal').classList.add('open')}
function closeModal(){$('#modal').classList.remove('open')}
$('#modal-form').onsubmit=async e=>{e.preventDefault();const f=e.target,t=f.dataset.type,d=Object.fromEntries(new FormData(f)),endpoint={patient:'patients',appointment:'appointments',record:'records',invoice:'invoices'}[t]||t;try{await api(endpoint,{method:'POST',body:JSON.stringify(d)});closeModal();toast('Saved successfully');go(t==='patient'?'patients':t==='appointment'?'appointments':t==='record'?'records':'billing')}catch(x){toast(x.message)}}
function showNotifications(){api('notifications').then(r=>alert(r.data.map(x=>x.title+': '+x.message).join('\n')))}
if(localStorage.getItem('medcore-user')) showApp();
</script>
<script src="https://cdn.botpress.cloud/webchat/v5.0/inject.js"></script>
<script src="https://files.bpcontent.cloud/2026/10/29/06/20261029065202-BS7QF7K4.js" defer></script>
</body></html>"""


def ensure_frontend():
    path = ROOT / "index.html"
    if not path.exists():
        path.write_text(HTML, encoding="utf-8")


if __name__ == "__main__":
    init_db()
    ensure_frontend()
    print(f"MedCore HMS running at http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()