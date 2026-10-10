
from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/")
def index():
    return jsonify({
        "application": "MURANG'A AGRIFLOW",
        "message": "Backend API is running",
        "health_endpoint": "/api/health"
    })


@app.get("/api/health")
def health_check():
    return jsonify({
        "status": "ok",
        "service": "muranga-agriflow-api",
        "version": "0.1.0"
    }), 200


if __name__ == "__main__":
    # Local development only; do not expose Flask's
    # development server to the public internet.
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=True
    )
