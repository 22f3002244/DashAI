from flask import Flask
from flask_socketio import SocketIO
from config import FLASK_SECRET, GROQ_API_KEY
from database import init_db
from routes import bp

app = Flask(__name__)
app.secret_key = FLASK_SECRET
app.register_blueprint(bp)

socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database on startup
with app.app_context():
    init_db()

# Make socketio accessible to routes
from routes import init_socketio
init_socketio(socketio)

if __name__ == "__main__":
    print("\n" + "─"*44)
    print("  ThingsBoard AI Dashboard (with Real-time)")
    print("  http://localhost:5050")
    print(f"  Groq AI: {'✓ configured' if GROQ_API_KEY and GROQ_API_KEY != 'your_groq_api_key_here' else '✗ not set (add key to .env)'}")
    print("─"*44 + "\n")
    socketio.run(app, debug=True, port=5050, allow_unsafe_werkzeug=True)
