import datetime
from functools import wraps
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from sqlalchemy import func
from models.database import User
import google.generativeai as genai
import re
from datetime import datetime
from google.api_core.exceptions import ServerError
import markdown
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv

user = Blueprint('user', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('You need to log in first.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def serialize_data(obj):
    if isinstance(obj, dict):
        return {k: serialize_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_data(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj
    
load_dotenv()  # Load variables from .env file
key = os.getenv("KEY")


# Gemini API key configuration
genai.configure(api_key=key)
model = genai.GenerativeModel("gemini-2.0-flash")

# Jinja2 environment for custom template-based prompts
jinja_env = Environment(loader=FileSystemLoader("templates"))


@user.route("/", methods=["GET", "POST"])
def index():
    response_text = ""
    formatted = ""
    user_text = ""

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if "chat_history" not in session:
        session["chat_history"] = []

    if request.method == "POST":
        user_text = request.form.get("user_input")

        # Use Jinja2 to render prompt from template
        template = jinja_env.get_template("prompt_template.txt")
        prompt = template.render(text=user_text, datetime=now)

        # Send to Gemini
        try:
            response = model.generate_content(prompt)
            response_text = response.text
            formatted = markdown.markdown(response_text)
        except ServerError as e:
            flash("⚠️ The AI model is currently overloaded. Please try again in a few minutes.")

        session["chat_history"].append({"user": user_text, "bot": response_text})
        session.modified = True  # Tell Flask to save the session

    return render_template("index.html", response = formatted, user_input=user_text, history=session["chat_history"])


@user.route("/chat", methods=["POST"])
def chat():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data = request.get_json()
    user_input = data.get("user_input", "")

    template = jinja_env.get_template("prompt_template.txt")
    prompt = template.render(text=user_input, datetime=now)

    try:
        response = model.generate_content(prompt)
        response_text = response.text
        formatted = markdown.markdown(response_text)
    except ServerError:
        return jsonify({"reply": "⚠️ The AI model is currently overloaded. Please try again in a few minutes."}), 503

    # Update session history
    if "chat_history" not in session:
        session["chat_history"] = []
    session["chat_history"].append({"user": user_input, "bot": response_text})
    session.modified = True

    return jsonify({"reply": formatted})

@user.route('/home')
def index2():
    flash('Welcome to Dash AI!', 'success')
    return render_template('base.html')
