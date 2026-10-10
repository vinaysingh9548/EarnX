from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Blogger website se connection allow karne ke liye CORS
CORS(app)

# Fake Database (Testing ke liye)
USER_DATA = {
    "balance": 15.00,
    "approved_tasks": 0
}

@app.route("/")
def home():
    return jsonify({"status": "Active", "message": "Backend Server Ready Hai!"})

@app.route("/api/user-data", methods=["GET"])
def get_user_data():
    return jsonify(USER_DATA)

@app.route("/api/withdraw", methods=["POST"])
def withdraw():
    data = request.json or {}
    amount = float(data.get("amount", 0))
    upi_id = data.get("upi_id", "")

    if amount < 50:
        return jsonify({"status": "error", "message": "Minimum ₹50 zaroori hai"}), 400

    if USER_DATA["balance"] < amount:
        return jsonify({"status": "error", "message": "Balance kam hai"}), 400

    USER_DATA["balance"] -= amount
    return jsonify({
        "status": "success",
        "message": f"₹{amount} Withdrawal Request UPI ({upi_id}) par submit ho gayi!",
        "new_balance": USER_DATA["balance"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)