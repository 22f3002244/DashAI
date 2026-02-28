import requests
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from config import GROQ_API_KEY, TB_PRESETS, TIME_RANGES
from database import get_db, log_agent, create_user, get_user_by_email, get_user_by_id
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
    c = get_db()
    rows = c.execute(
        "SELECT agent_name,status,message,created_at FROM agent_logs "
        "WHERE session_id=? ORDER BY created_at", (session_id,)
    ).fetchall()
    c.close()
    return jsonify([dict(r) for r in rows])
