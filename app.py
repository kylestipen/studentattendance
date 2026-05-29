"""
StudentBase — Live Attendance & Monitoring System
app.py  ·  Flask + Flask-SocketIO backend
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_socketio import SocketIO, emit
import mysql.connector
from mysql.connector import Error
from datetime import date, datetime, timedelta
from functools import wraps
import secrets
import os

# ─── App Setup ───────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'studentbase-secret-2024')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ─── DB Config ───────────────────────────────────────────────
DB_CONFIG = {
    'host':     os.environ.get('DB_HOST',   'localhost'),
    'user':     os.environ.get('DB_USER',   'root'),
    'password': os.environ.get('DB_PASS',   ''),
    'database': os.environ.get('DB_NAME',   'studentbase'),
    'charset':  'utf8mb4',
}

def get_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"[DB ERROR] {e}")
        return None

def query(sql, params=(), fetchone=False, commit=False):
    conn = get_db()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        if commit:
            conn.commit()
            return cur.lastrowid
        return cur.fetchone() if fetchone else cur.fetchall()
    except Error as e:
        print(f"[QUERY ERROR] {e}")
        return None
    finally:
        conn.close()

# ─── Auth Decorators ─────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return redirect(url_for('my_profile'))
        return f(*args, **kwargs)
    return decorated

# ─── Helpers ─────────────────────────────────────────────────
def get_student_stats(student_id):
    rows = query(
        "SELECT status FROM attendance WHERE student_id=%s ORDER BY date DESC",
        (student_id,)
    ) or []
    total   = len(rows)
    present = sum(1 for r in rows if r['status'] == 'Present')
    late    = sum(1 for r in rows if r['status'] == 'Late')
    absent  = sum(1 for r in rows if r['status'] == 'Absent')
    pct     = round((present + late) / total * 100) if total else 0

    # consecutive absences (most recent first)
    consec = 0
    for r in rows:
        if r['status'] == 'Absent':
            consec += 1
        else:
            break

    return {
        'total': total, 'present': present, 'late': late,
        'absent': absent, 'pct': pct, 'consecutive_absences': consec,
        'at_risk': consec >= 3 or absent >= 5 or pct < 75
    }

def add_notification(message, ntype='info', student_id=None):
    nid = query(
        "INSERT INTO notifications (message, type, student_id) VALUES (%s,%s,%s)",
        (message, ntype, student_id), commit=True
    )
    # broadcast to all admins
    notif = {
        'id': nid, 'message': message, 'type': ntype,
        'student_id': student_id,
        'created_at': datetime.now().strftime('%H:%M')
    }
    socketio.emit('new_notification', notif)
    return nid

def check_and_flag_student(student_id, student_name):
    stats = get_student_stats(student_id)
    if stats['consecutive_absences'] == 3:
        add_notification(f"⚠️ {student_name} has 3 consecutive absences — AT RISK", 'warning', student_id)
    if stats['absent'] == 5:
        add_notification(f"🔴 {student_name} has 5 total absences — needs intervention", 'danger', student_id)
    if stats['pct'] < 75 and stats['total'] >= 5:
        add_notification(f"📉 {student_name} is below 75% attendance ({stats['pct']}%)", 'warning', student_id)

# ─── Routes: Auth ────────────────────────────────────────────
@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = query(
            "SELECT * FROM sqlusers WHERE username=%s AND password=%s",
            (username, password), fetchone=True
        )
        if user:
            session['user_id']    = user['id']
            session['username']   = user['username']
            session['role']       = user['role']
            session['student_id'] = user['student_id']
            if user['role'] == 'admin':
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('my_profile'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── Routes: Admin ───────────────────────────────────────────
@app.route('/dashboard')
@login_required
@admin_required
def dashboard():
    today = date.today().isoformat()

    # today's counts
    today_rows = query(
        "SELECT status, COUNT(*) as cnt FROM attendance WHERE date=%s GROUP BY status",
        (today,)
    ) or []
    counts = {'Present': 0, 'Absent': 0, 'Late': 0}
    for r in today_rows:
        counts[r['status']] = r['cnt']

    total_students = (query("SELECT COUNT(*) as n FROM students", fetchone=True) or {}).get('n', 0)
    counts['not_recorded'] = total_students - sum(counts.values())

    # at-risk students
    all_students = query("SELECT * FROM students") or []
    at_risk = []
    for s in all_students:
        stats = get_student_stats(s['id'])
        if stats['at_risk']:
            s['stats'] = stats
            at_risk.append(s)

    # recent activity (today)
    recent = query(
        """SELECT a.*, s.first_name, s.last_name, s.student_number
           FROM attendance a JOIN students s ON a.student_id=s.id
           WHERE a.date=%s AND a.scanned_at IS NOT NULL
           ORDER BY a.scanned_at DESC LIMIT 10""",
        (today,)
    ) or []

    # chart: last 7 days
    chart_labels, chart_present, chart_absent, chart_late = [], [], [], []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        row = query(
            """SELECT
                SUM(status='Present') as p,
                SUM(status='Absent')  as a,
                SUM(status='Late')    as l
               FROM attendance WHERE date=%s""",
            (d,), fetchone=True
        ) or {}
        chart_labels.append(d[5:])  # MM-DD
        chart_present.append(int(row.get('p') or 0))
        chart_absent.append(int(row.get('a') or 0))
        chart_late.append(int(row.get('l') or 0))

    notifications = query(
        "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 20"
    ) or []
    unread = query(
        "SELECT COUNT(*) as n FROM notifications WHERE is_read=0",
        fetchone=True
    ) or {'n': 0}

    return render_template('dashboard.html',
        counts=counts, at_risk=at_risk, recent=recent,
        chart_labels=chart_labels, chart_present=chart_present,
        chart_absent=chart_absent, chart_late=chart_late,
        notifications=notifications, unread=unread['n'],
        today=today, total_students=total_students
    )

@app.route('/students')
@login_required
@admin_required
def students():
    all_students = query("SELECT * FROM students ORDER BY last_name, first_name") or []
    enriched = []
    for s in all_students:
        s['stats'] = get_student_stats(s['id'])
        enriched.append(s)
    return render_template('students.html', students=enriched)

@app.route('/students/add', methods=['POST'])
@login_required
@admin_required
def add_student():
    data = request.form
    token = secrets.token_hex(16)
    sid = query(
        """INSERT INTO students (student_number,first_name,last_name,email,course,year_level,section,qr_token)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (data['student_number'], data['first_name'], data['last_name'],
         data['email'], data['course'], data['year_level'], data['section'], token),
        commit=True
    )
    # create login
    query(
        "INSERT INTO sqlusers (username,password,role,student_id) VALUES (%s,%s,'student',%s)",
        (data['student_number'], data['student_number'], sid), commit=True
    )
    flash('Student added successfully', 'success')
    return redirect(url_for('students'))

@app.route('/students/delete/<int:sid>', methods=['POST'])
@login_required
@admin_required
def delete_student(sid):
    query("DELETE FROM students WHERE id=%s", (sid,), commit=True)
    flash('Student removed', 'info')
    return redirect(url_for('students'))

@app.route('/attendance')
@login_required
@admin_required
def attendance():
    today = date.today().isoformat()
    all_students = query("SELECT * FROM students ORDER BY last_name, first_name") or []
    board = []
    for s in all_students:
        rec = query(
            "SELECT * FROM attendance WHERE student_id=%s AND date=%s",
            (s['id'], today), fetchone=True
        )
        s['today'] = rec
        board.append(s)
    return render_template('attendance.html', board=board, today=today)

@app.route('/attendance/override', methods=['POST'])
@login_required
@admin_required
def override_attendance():
    data = request.get_json()
    student_id = data['student_id']
    new_status = data['status']
    today = date.today().isoformat()

    existing = query(
        "SELECT id FROM attendance WHERE student_id=%s AND date=%s",
        (student_id, today), fetchone=True
    )
    if existing:
        query(
            "UPDATE attendance SET status=%s, notes='Manual override' WHERE student_id=%s AND date=%s",
            (new_status, student_id, today), commit=True
        )
    else:
        query(
            "INSERT INTO attendance (student_id,date,status,notes) VALUES (%s,%s,%s,'Manual override')",
            (student_id, today, new_status), commit=True
        )

    student = query("SELECT * FROM students WHERE id=%s", (student_id,), fetchone=True)
    name = f"{student['first_name']} {student['last_name']}"

    socketio.emit('attendance_update', {
        'student_id': student_id,
        'student_name': name,
        'student_number': student['student_number'],
        'status': new_status,
        'time': datetime.now().strftime('%H:%M'),
        'method': 'override'
    })
    add_notification(f"✏️ {name} manually set to {new_status}", 'info', student_id)
    return jsonify({'ok': True, 'status': new_status})

@app.route('/reports')
@login_required
@admin_required
def reports():
    all_students = query("SELECT * FROM students ORDER BY last_name, first_name") or []
    enriched = []
    for s in all_students:
        s['stats'] = get_student_stats(s['id'])
        s['history'] = query(
            "SELECT * FROM attendance WHERE student_id=%s ORDER BY date DESC LIMIT 14",
            (s['id'],)
        ) or []
        enriched.append(s)

    # summary by date (last 14 days)
    daily = []
    for i in range(13, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        row = query(
            """SELECT date,
                SUM(status='Present') as present,
                SUM(status='Absent')  as absent,
                SUM(status='Late')    as late
               FROM attendance WHERE date=%s""",
            (d,), fetchone=True
        ) or {}
        daily.append({
            'date': d, 'present': int(row.get('present') or 0),
            'absent': int(row.get('absent') or 0),
            'late': int(row.get('late') or 0)
        })

    return render_template('reports.html', students=enriched, daily=daily)

# ─── Routes: Student ─────────────────────────────────────────
@app.route('/my-qr')
@login_required
def my_qr():
    if session['role'] == 'admin':
        return redirect(url_for('dashboard'))
    student = query("SELECT * FROM students WHERE id=%s", (session['student_id'],), fetchone=True)
    return render_template('my_qr.html', student=student)

@app.route('/my-profile')
@login_required
def my_profile():
    if session['role'] == 'admin':
        return redirect(url_for('dashboard'))
    student = query("SELECT * FROM students WHERE id=%s", (session['student_id'],), fetchone=True)
    stats   = get_student_stats(session['student_id'])
    history = query(
        "SELECT * FROM attendance WHERE student_id=%s ORDER BY date DESC LIMIT 30",
        (session['student_id'],)
    ) or []
    return render_template('my_profile.html', student=student, stats=stats, history=history)

# ─── API: QR Scan ────────────────────────────────────────────
@app.route('/api/scan', methods=['POST'])
def api_scan():
    data  = request.get_json()
    token = data.get('token', '').strip()
    today = date.today().isoformat()
    now   = datetime.now()

    student = query("SELECT * FROM students WHERE qr_token=%s", (token,), fetchone=True)
    if not student:
        return jsonify({'ok': False, 'error': 'Unknown QR code'}), 400

    existing = query(
        "SELECT * FROM attendance WHERE student_id=%s AND date=%s",
        (student['id'], today), fetchone=True
    )
    if existing and existing['status'] == 'Present':
        return jsonify({'ok': True, 'already': True,
                        'student_name': f"{student['first_name']} {student['last_name']}",
                        'status': 'Present'})

    # determine Late: after 08:30
    status = 'Late' if now.hour > 8 or (now.hour == 8 and now.minute >= 30) else 'Present'

    if existing:
        query(
            "UPDATE attendance SET status=%s, scanned_at=%s WHERE student_id=%s AND date=%s",
            (status, now, student['id'], today), commit=True
        )
    else:
        query(
            "INSERT INTO attendance (student_id,date,status,scanned_at) VALUES (%s,%s,%s,%s)",
            (student['id'], today, status, now), commit=True
        )

    name = f"{student['first_name']} {student['last_name']}"
    emoji = "✅" if status == 'Present' else "🕐"
    add_notification(f"{emoji} {name} marked {status}", 'info', student['id'])
    check_and_flag_student(student['id'], name)

    payload = {
        'student_id':     student['id'],
        'student_name':   name,
        'student_number': student['student_number'],
        'status':         status,
        'time':           now.strftime('%H:%M'),
        'method':         'qr_scan'
    }
    socketio.emit('attendance_update', payload)

    return jsonify({'ok': True, 'student_name': name, 'status': status,
                    'time': now.strftime('%H:%M')})

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifications_read():
    query("UPDATE notifications SET is_read=1", commit=True)
    return jsonify({'ok': True})

@app.route('/api/dashboard-stats')
@login_required
@admin_required
def dashboard_stats():
    today = date.today().isoformat()
    rows = query(
        "SELECT status, COUNT(*) as cnt FROM attendance WHERE date=%s GROUP BY status", (today,)
    ) or []
    counts = {'Present': 0, 'Absent': 0, 'Late': 0}
    for r in rows:
        counts[r['status']] = r['cnt']
    total = (query("SELECT COUNT(*) as n FROM students", fetchone=True) or {}).get('n', 0)
    unread = (query("SELECT COUNT(*) as n FROM notifications WHERE is_read=0", fetchone=True) or {}).get('n', 0)
    return jsonify({'counts': counts, 'total': total, 'unread': unread})

# ─── SocketIO Events ─────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    emit('connected', {'msg': 'StudentBase live connection established'})

@socketio.on('ping_server')
def on_ping():
    emit('pong_server', {'time': datetime.now().strftime('%H:%M:%S')})

# ─── Run ─────────────────────────────────────────────────────
if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
