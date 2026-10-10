import sqlite3
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ADMIN_PASSWORD = "admin123"  # <-- Aapka Admin Password

def get_db():
    conn = sqlite3.connect('earnx.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # Users Table
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT,
            balance REAL DEFAULT 15.0,
            referrals INTEGER DEFAULT 0,
            referred_by TEXT DEFAULT '',
            is_blocked INTEGER DEFAULT 0
        )''')
        
        # Tasks Table
        conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            reward REAL,
            category TEXT,
            description TEXT,
            link TEXT,
            status TEXT DEFAULT 'active'
        )''')

        # Task Submissions Table
        conn.execute('''CREATE TABLE IF NOT EXISTS task_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            user_id TEXT,
            proof_text TEXT,
            reward REAL,
            status TEXT DEFAULT 'pending',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Withdrawals Table
        conn.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            upi_id TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending',
            txn_ref TEXT DEFAULT '',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()

init_db()

# --- ADMIN CHECK HELPER ---
def check_admin(req):
    if req.method == 'GET':
        pwd = req.args.get('password')
    else:
        data = req.json or {}
        pwd = data.get('password')
    return pwd == ADMIN_PASSWORD

# --- BASE ROUTE ---
@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "EarnX Backend Live!", "status": "Active"})

# --- USER AUTO SIGNUP & LOGIN API ---

@app.route('/api/user-data', methods=['GET'])
def get_user_data():
    user_id = request.args.get('user_id')
    user_name = request.args.get('name', 'Telegram User')
    ref_by = request.args.get('ref_by', '')

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        
        # AGAR USER NAYA HAI TOH AUTOMATIC SIGNUP / DB INSERT KAREIN
        if not user:
            conn.execute('INSERT INTO users (id, name, balance, referred_by) VALUES (?, ?, ?, ?)', 
                         (user_id, user_name, 15.0, ref_by))
            
            # Agar kisi ke referral link se aaya hai toh referrer ko ₹5 bonus credit karein
            if ref_by and ref_by != user_id:
                conn.execute('UPDATE users SET balance = balance + 5.0, referrals = referrals + 1 WHERE id = ?', (ref_by,))
            
            conn.commit()
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        
        if user['is_blocked'] == 1:
            return jsonify({"error": "blocked", "message": "Aapka account block kar diya gaya hai. Support se sampark karein."}), 403

        return jsonify(dict(user))

@app.route('/api/submit-task', methods=['POST'])
def submit_task():
    data = request.json or {}
    user_id = data.get('user_id')
    task_id = data.get('task_id')
    proof_text = data.get('proof_text', '')

    with get_db() as conn:
        user = conn.execute('SELECT is_blocked FROM users WHERE id = ?', (user_id,)).fetchone()
        if user and user['is_blocked'] == 1:
            return jsonify({"message": "Account blocked!"}), 403

        task = conn.execute('SELECT reward FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            return jsonify({"message": "Invalid task"}), 400

        conn.execute('INSERT INTO task_submissions (task_id, user_id, proof_text, reward) VALUES (?, ?, ?, ?)',
                     (task_id, user_id, proof_text, task['reward']))
        conn.commit()
        return jsonify({"message": "Task proof submitted successfully!"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json or {}
    user_id = data.get('user_id')
    upi_id = data.get('upi_id')
    amount = float(data.get('amount', 0))

    if not upi_id or amount < 50:
        return jsonify({"message": "Minimum withdrawal limit is ₹50.00"}), 400

    with get_db() as conn:
        user = conn.execute('SELECT balance, is_blocked FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user or user['is_blocked'] == 1:
            return jsonify({"message": "Account blocked or not found!"}), 403

        if user['balance'] < amount:
            return jsonify({"message": "Insufficient balance"}), 400

        new_balance = user['balance'] - amount
        conn.execute('UPDATE users SET balance = ? WHERE id = ?', (new_balance, user_id))
        conn.execute('INSERT INTO withdrawals (user_id, upi_id, amount) VALUES (?, ?, ?)', (user_id, upi_id, amount))
        conn.commit()

        return jsonify({"message": "Withdrawal request submitted successfully!", "new_balance": new_balance})

# --- ADMIN APIS ---

@app.route('/admin/users', methods=['GET'])
def admin_users():
    if not check_admin(request): return jsonify({"message": "Unauthorized"}), 401
    with get_db() as conn:
        users = conn.execute('SELECT * FROM users ORDER BY balance DESC').fetchall()
        return jsonify([dict(u) for u in users])

@app.route('/admin/toggle-block-user', methods=['POST'])
def admin_toggle_block():
    if not check_admin(request): return jsonify({"message": "Unauthorized"}), 401
    data = request.json or {}
    user_id = data.get('user_id')
    block_status = data.get('is_blocked')
    with get_db() as conn:
        conn.execute('UPDATE users SET is_blocked = ? WHERE id = ?', (block_status, user_id))
        conn.commit()
    return jsonify({"message": "User status updated successfully!"})

@app.route('/admin/adjust-balance', methods=['POST'])
def admin_adjust_balance():
    if not check_admin(request): return jsonify({"message": "Unauthorized"}), 401
    data = request.json or {}
    user_id = data.get('user_id')
    amount = float(data.get('amount', 0))
    with get_db() as conn:
        conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, user_id))
        conn.commit()
    return jsonify({"message": "User wallet balance updated!"})

@app.route('/admin/task-submissions', methods=['GET'])
def admin_task_submissions():
    if not check_admin(request): return jsonify({"message": "Unauthorized"}), 401
    with get_db() as conn:
        rows = conn.execute('''SELECT ts.*, t.title as task_title FROM task_submissions ts 
                               LEFT JOIN tasks t ON ts.task_id = t.id 
                               ORDER BY ts.id DESC''').fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/admin/review-task-submission', methods=['POST'])
def admin_review_task_submission():
    if not check_admin(request): return jsonify({"message": "Unauthorized"}), 401
    data = request.json or {}
    sub_id = data.get('submission_id')
    status = data.get('status')

    with get_db() as conn:
        sub = conn.execute('SELECT * FROM task_submissions WHERE id = ?', (sub_id,)).fetchone()
        if not sub or sub['status'] != 'pending':
            return jsonify({"message": "Invalid or already processed submission"}), 400

        conn.execute('UPDATE task_submissions SET status = ? WHERE id = ?', (status, sub_id))
        if status == 'approved':
            conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (sub['reward'], sub['user_id']))
        conn.commit()

    return jsonify({"message": f"Task proof {status}!"})

@app.route('/admin/withdrawals', methods=['GET'])
def admin_get_withdrawals():
    if not check_admin(request): return jsonify({"message": "Unauthorized"}), 401
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM withdrawals ORDER BY id DESC').fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/admin/update-withdrawal', methods=['POST'])
def admin_update_withdrawal():
    if not check_admin(request): return jsonify({"message": "Unauthorized"}), 401
    data = request.json or {}
    w_id = data.get('id')
    status = data.get('status')
    txn_ref = data.get('txn_ref', '')

    with get_db() as conn:
        if status == 'rejected':
            item = conn.execute('SELECT user_id, amount FROM withdrawals WHERE id = ?', (w_id,)).fetchone()
            if item:
                conn.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (item['amount'], item['user_id']))
        
        conn.execute('UPDATE withdrawals SET status = ?, txn_ref = ? WHERE id = ?', (status, txn_ref, w_id))
        conn.commit()

    return jsonify({"message": f"Withdrawal status updated to {status}"})

@app.route('/admin/add-task', methods=['POST'])
def admin_add_task():
    if not check_admin(request): return jsonify({"message": "Unauthorized"}), 401
    data = request.json or {}
    with get_db() as conn:
        conn.execute('''INSERT INTO tasks (title, reward, category, description, link) 
                        VALUES (?, ?, ?, ?, ?)''', 
                     (data['title'], data['reward'], data['category'], data['description'], data['link']))
        conn.commit()
    return jsonify({"message": "Task added successfully!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
