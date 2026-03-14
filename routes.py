import requests
import json
import secrets
import time
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

from config import GROQ_API_KEY, TB_PRESETS, TIME_RANGES
from database import get_db, log_agent, create_user, get_user_by_email, get_user_by_id, get_session_logs, save_dashboard, get_dashboards, get_dashboard, delete_dashboard, get_dashboard_by_token
from pipeline import run_pipeline

bp = Blueprint("main", __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("main.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def tb_login(host, username, password):
    r = requests.post(
        f"{host}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15)
    if r.status_code == 401:
        raise ValueError("Wrong email or password. Please check your credentials.")
    if r.status_code != 200:
        raise ValueError(f"ThingsBoard returned HTTP {r.status_code}. Check the server URL.")
    return r.json().get("token")

@bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template("register.html", error="All fields are required")

        if create_user(email, generate_password_hash(password)):
            return redirect(url_for("main.login"))
        else:
            return render_template("register.html", error="Email already exists")

    return render_template("register.html")

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("main.dashboard"))
        else:
            return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@bp.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("main.index"))

@bp.route("/dashboard")
@login_required
def dashboard():
    groq_configured = bool(GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here")
    user = get_user_by_id(session["user_id"])
    return render_template("dashboard.html",
                           time_ranges=TIME_RANGES,
                           tb_presets=TB_PRESETS,
                           groq_configured=groq_configured,
                           user_email=user["email"])

@bp.route("/api/login", methods=["POST"])
def api_login():
    d = request.json or {}
    host     = d.get("tb_host","").strip().rstrip("/")
    email    = d.get("email","").strip()
    password = d.get("password","").strip()
    token    = d.get("token","").strip()

    if not host: return jsonify({"error": "Please enter the server address."}), 400
    if not host.startswith("http"): host = "https://" + host

    try:
        if token:
            r = requests.get(f"{host}/api/auth/user",
                             headers={"X-Authorization": f"Bearer {token}"}, timeout=10)
            if r.status_code != 200:
                return jsonify({"error": "Invalid token. Please check and try again."}), 401
            user = r.json()
            first = user.get("firstName") or ""
            last = user.get("lastName") or ""
            return jsonify({"token": token,
                            "email": user.get("email",""),
                            "name": (first + " " + last).strip()})
        elif email and password:
            tok = tb_login(host, email, password)
            r2  = requests.get(f"{host}/api/auth/user",
                               headers={"X-Authorization": f"Bearer {tok}"}, timeout=10)
            user = r2.json() if r2.status_code == 200 else {}
            first = user.get("firstName") or ""
            last = user.get("lastName") or ""
            name = (first + " " + last).strip() or email
            return jsonify({"token": tok, "email": email, "name": name})
        else:
            return jsonify({"error": "Please enter your email and password."}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    except requests.exceptions.ConnectionError:
        return jsonify({"error": f"Cannot connect to '{host}'. Check the server address."}), 400
    except Exception as e:
        return jsonify({"error": f"Login failed: {e}"}), 400

@bp.route("/api/devices", methods=["POST"])
@login_required
def api_devices():
    d     = request.json or {}
    host  = d.get("tb_host","").strip().rstrip("/")
    token = d.get("token","").strip()
    if not host.startswith("http"): host = "https://" + host
    try:
        r = requests.get(f"{host}/api/tenant/devices",
                         headers={"X-Authorization": f"Bearer {token}"},
                         params={"pageSize": 100, "page": 0}, timeout=15)
        if r.status_code == 200:
            devs = r.json().get("data", [])
            return jsonify({"devices": [{"id": d["id"]["id"], "name": d.get("name",""), "type": d.get("type","")} for d in devs]})
        r2 = requests.get(f"{host}/api/user",
                          headers={"X-Authorization": f"Bearer {token}"}, timeout=10)
        if r2.status_code == 200:
            uid = r2.json().get("customerId",{}).get("id","")
            if uid and uid != "13814000-1dd2-11b2-8080-808080808080":
                r3 = requests.get(f"{host}/api/customer/{uid}/devices",
                                  headers={"X-Authorization": f"Bearer {token}"},
                                  params={"pageSize": 100, "page": 0}, timeout=15)
                if r3.status_code == 200:
                    devs = r3.json().get("data", [])
                    return jsonify({"devices": [{"id": d["id"]["id"], "name": d.get("name",""), "type": d.get("type","")} for d in devs]})
        return jsonify({"devices": [], "warning": "Could not list devices. You can still enter a Device ID manually."})
    except Exception as e:
        return jsonify({"devices": [], "warning": f"Device list unavailable: {e}"}), 200

@bp.route("/run", methods=["POST"])
@login_required
def run_dashboard():
    d          = request.json or {}
    tb_host    = d.get("tb_host","").strip().rstrip("/")
    tb_token   = d.get("tb_token","").strip()
    device_id  = d.get("device_id","").strip()
    time_range = d.get("time_range","24h")

    if not tb_host.startswith("http"): tb_host = "https://" + tb_host
    if not all([tb_host, tb_token, device_id]):
        return jsonify({"error": "Missing required fields."}), 400
    if time_range not in TIME_RANGES:
        return jsonify({"error": "Invalid time range."}), 400

    state = run_pipeline(tb_host, tb_token, device_id, time_range)
    if not state.get("dashboard_data") and state["errors"]:
        return jsonify({"error": state["errors"][0]}), 400

    return jsonify({"session_id":      state["session_id"],
                    "agent_statuses":  state["agent_statuses"],
                    "errors":          state["errors"],
                    "warnings":        state.get("warnings",[]),
                    "dashboard_data":  state.get("dashboard_data",{})})

@bp.route("/logs/<session_id>")
@login_required
def get_logs(session_id):
    rows = get_session_logs(session_id)
    return jsonify(rows)

@bp.route("/api/dashboards", methods=["GET", "POST"])
@login_required
def api_dashboards():
    if request.method == "GET":
        dashboards = get_dashboards(session["user_id"])
        return jsonify(dashboards)
    
    if request.method == "POST":
        d = request.json or {}
        name = d.get("name", "").strip()
        config = d.get("config")
        
        if not name or not config:
            return jsonify({"error": "Name and config are required."}), 400
            
        # Ensure config is a string
        if not isinstance(config, str):
            config = json.dumps(config)
            
        share_token = secrets.token_urlsafe(16)
        dashboard_id = save_dashboard(session["user_id"], name, config, share_token)
        
        return jsonify({
            "message": "Dashboard saved successfully.",
            "id": dashboard_id,
            "share_token": share_token
        })

@bp.route("/api/dashboards/<int:dashboard_id>", methods=["GET", "DELETE"])
@login_required
def api_dashboard_detail(dashboard_id):
    if request.method == "GET":
        dashboard = get_dashboard(dashboard_id, session["user_id"])
        if not dashboard:
            return jsonify({"error": "Dashboard not found."}), 404
        return jsonify(dashboard)
        
    if request.method == "DELETE":
        if delete_dashboard(dashboard_id, session["user_id"]):
            return jsonify({"message": "Dashboard deleted successfully."})
        return jsonify({"error": "Failed to delete dashboard."}), 500

@bp.route("/share/<token>")
def shared_dashboard(token):
    dashboard = get_dashboard_by_token(token)
    if not dashboard:
        return render_template("error.html", message="This shared dashboard link is invalid or has been removed."), 404
        
    groq_configured = bool(GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here")
    
    # Render the dashboard template but indicate it's a shared (read-only) view
    return render_template("dashboard.html",
                           time_ranges=TIME_RANGES,
                           tb_presets=TB_PRESETS,
                           groq_configured=groq_configured,
                           user_email=dashboard.get("owner_email", "Shared User"),
                           shared_dashboard=dashboard)

@bp.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    d = request.json or {}
    message = d.get("message", "").strip()
    context = d.get("context", {})
    history = d.get("history", [])
    
    if not message:
        return jsonify({"error": "Message is required."}), 400
        
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        return jsonify({"error": "Groq API key not configured."}), 400
        
    # Build prompt context
    device_name = context.get("device_name", "IoT Device")
    system_prompt = f"""You are a helpful IoT Data Analyst AI named Ubie.
You are helping a user understand their '{device_name}' dashboard data.

Dashboard Overview:
- Device Type: {context.get("device_type", "Unknown")}
- Time Range Analysed: {context.get("time_range_label", "Unknown")}
- Total Data Points: {context.get("total_points", 0):,}
- Numeric Sensors: {context.get("numeric_count", 0)}, Boolean Sensors: {context.get("boolean_count", 0)}

Sensor Statistics (min, max, average, trend):
"""
    # Include detailed kpi_cards data for precise Q&A
    from datetime import datetime
    for kpi in context.get("kpi_cards", []):
        label = kpi.get("label", "?")
        unit = kpi.get("unit", "")
        u = f" {unit}" if unit else ""
        avg = kpi.get("avg","?")
        mn = kpi.get("min","?")
        mx = kpi.get("max","?")
        trend = kpi.get("trend","?")
        anom = kpi.get("anomaly_count", 0)
        # Try to get timestamps for min/max if available
        min_ts = kpi.get("min_ts")
        max_ts = kpi.get("max_ts")
        max_str = f"{mx}{u}"
        min_str = f"{mn}{u}"
        if max_ts:
            try: max_str += f" at {datetime.fromtimestamp(int(max_ts)/1000).strftime('%H:%M on %d %b')}"
            except: pass
        if min_ts:
            try: min_str += f" at {datetime.fromtimestamp(int(min_ts)/1000).strftime('%H:%M on %d %b')}"
            except: pass
        system_prompt += f"- {label}: avg={avg}{u}, min={min_str}, max={max_str}, trend={trend}"
        if anom > 0:
            system_prompt += f", {anom} anomalies detected"
        system_prompt += "\n"

    system_prompt += "\nKey Patterns & Insights:\n"
    for p in context.get("patterns", []):
        system_prompt += f"- [{p.get('type','?').upper()}] {p.get('description','')}\n"
        
    system_prompt += "\nAnswer the user's question accurately based on the data above. If you can give a precise value with timestamp, do so. Be concise and direct."

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-5:]:  # keep last 5 messages for context
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 512
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=12)
        if r.status_code == 200:
            reply = r.json()["choices"][0]["message"]["content"]
            return jsonify({"reply": reply})
        else:
            return jsonify({"error": f"AI Error: {r.text}"}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to connect to AI: {e}"}), 500


# ---------------------------------------------------------
# Real-Time Telemetry Streaming via WebSockets
# ---------------------------------------------------------
socketio_instance = None
active_sessions = {}  # request.sid -> dict
scheduler = BackgroundScheduler()

def fetch_live_telemetry():
    """Background job that queries ThingsBoard for latest telemetry values for all active WebSocket sessions"""
    if not socketio_instance or not active_sessions:
        return
        
    for sid, info in list(active_sessions.items()):
        try:
            url = f"{info['host']}/api/plugins/telemetry/DEVICE/{info['device_id']}/values/timeseries"
            r = requests.get(url, headers={"X-Authorization": f"Bearer {info['token']}"}, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data:
                    socketio_instance.emit('telemetry_update', data, to=sid)
        except Exception:
            pass

scheduler.add_job(fetch_live_telemetry, 'interval', seconds=3)
scheduler.start()

def init_socketio(sio):
    global socketio_instance
    socketio_instance = sio
    
    @sio.on('connect')
    def handle_connect():
        pass
        
    @sio.on('disconnect')
    def handle_disconnect():
        active_sessions.pop(request.sid, None)

    @sio.on('subscribe_telemetry')
    def handle_subscribe(data):
        host = data.get('tb_host')
        token = data.get('tb_token')
        device_id = data.get('device_id')
        
        if host and token and device_id:
            if not host.startswith("http"):
                host = "https://" + host
            active_sessions[request.sid] = {
                'host': host.rstrip("/"),
                'token': token,
                'device_id': device_id
            }

