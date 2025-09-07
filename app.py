from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify, send_from_directory
import sqlite3
import os
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image
import json  # For handling AI response
import google.generativeai as genai

# Gemini API configuration
GEMINI_API_KEY = "AIzaSyD6OUxkcs7fsphPDZspNCbiyKU8OIM9EnQ"  # Replace with your actual key or use env variable
genai.configure(api_key=GEMINI_API_KEY)

SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

app = Flask(__name__)
app.secret_key = "supersecretkey"
DB_NAME = "resquick.db"
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# -------------------------
# Database Initialization
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aadhaar TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    mobile TEXT NOT NULL,
                    password TEXT NOT NULL
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    gram_panchayat TEXT,
                    block TEXT,
                    police_station TEXT,
                    district TEXT,
                    state TEXT,
                    latitude TEXT,
                    longitude TEXT,
                    datetime TEXT,
                    file_path TEXT,
                    status TEXT DEFAULT 'Pending',
                    damage_percentage REAL,
                    compensation_amount REAL,
                    reasoning TEXT,
                    recommendations TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )''')
    conn.commit()
    conn.close()

# -------------------------
# Officials Credentials
# -------------------------
officials = {
    "19472003": "Vishma@0101",
    "19472004": "Subhendu@42",
    "19472006": "Binay@2006",
    "19472005": "Anisha@2005"
}

# -------------------------
# Custom PDF Class
# -------------------------
class ApplicationPDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 18)
        self.cell(0, 10, 'Help Application Report', 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, align='C')

    def application_body(self, data):
        field_map = {
            "name": "Full Name",
            "gram_panchayat": "Gram Panchayat",
            "block": "Block",
            "police_station": "Police Station",
            "district": "District",
            "state": "State",
            "latitude": "Latitude",
            "longitude": "Longitude",
            "datetime": "Date & Time of Submission",
            "status": "Application Status",
            "damage_percentage": "AI Assessed Damage (%)",
            "compensation_amount": "AI Estimated Compensation (INR)",
            "reasoning": "AI Damage Analysis",
            "recommendations": "AI Recommendations"
        }

        self.set_font('Helvetica', 'B', 12)
        self.cell(60, 10, 'Field', 1, align='C')
        self.cell(0, 10, 'Details', 1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        self.set_font('Helvetica', '', 11)
        for key, label in field_map.items():
            value = data.get(key)
            if key == "damage_percentage" and value is not None:
                value = f"{value:.2f}%"
            if key == "compensation_amount" and value is not None:
                value = f"₹ {value:,.2f}"
            if value is None or value == '':
                value = 'N/A'
            self.cell(60, 8, label, 1)
            self.multi_cell(150, 8, str(value), 1)


        file_paths_str = data.get("file_path")
        if file_paths_str:
            file_paths = file_paths_str.split(',')
            for file_path in file_paths:
                if file_path and os.path.exists(file_path.strip()):
                    self.add_page()
                    self.set_font('Helvetica', 'B', 14)
                    self.cell(0, 10, "Attached Evidence", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
                    self.ln(5)
                    try:
                        self.image(file_path.strip(), w=180)
                    except Exception as e:
                        self.set_font('Helvetica', 'I', 10)
                        self.cell(0, 10, f"Could not load image: {os.path.basename(file_path)} | Error: {e}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

# -------------------------
# AI Analysis Function
# -------------------------
def analyze_disaster_image(image_path):
    try:
        model = genai.GenerativeModel("models/gemini-1.5-flash")
        img = Image.open(image_path)
        prompt = """
        You are a senior disaster damage assessor with expertise in structural evaluation and compensation planning for disaster-affected areas.
        Analyze the provided image carefully and follow these instructions:

        1. Assess the severity of structural damage including collapsed walls, broken roofs, water damage, and other visible signs.
        2. Provide a detailed explanation describing what happened to the property, highlighting the major issues like roof loss, wall cracks, waterlogging, etc.
        3. Estimate the percentage of damage to the property based on visual evidence.
        4. Calculate the compensation amount in Indian Rupees (INR) using this formula: Compensation = (Damage Percentage / 100) * 150000.
        5. Suggest the main points the authorities should focus on while transferring funds through Direct Benefit Transfer (DBT), such as repair priorities and safety measures.
        6. Provide the output ONLY in the following JSON format without any additional commentary or explanation:

        {
          "damage_percentage": <number between 0 and 100>,
          "reasoning": "<detailed explanation of the damage>",
          "estimated_compensation": <calculated amount>,
          "recommendations": "<key points for DBT and repair>"
        }

        If the image does not show a damaged property or is irrelevant, return 0 for all numeric fields and an appropriate explanation.
        """
        response = model.generate_content([prompt, img], safety_settings=SAFETY_SETTINGS)
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        analysis_result = json.loads(cleaned_response)
        return {"success": True, "data": analysis_result}
    except Exception as e:
        print(f"Error during AI analysis: {e}")
        return {"success": False, "message": str(e)}

# -------------------------
# Routes
# -------------------------
@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/")
def login_option():
    return render_template("login_option.html")

@app.route("/user_login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        aadhaar = request.form.get("aadhaar")
        password = request.form.get("password")
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE aadhaar=? AND password=?", (aadhaar, password))
        user = c.fetchone()
        conn.close()
        if user:
            session["user_id"] = user[0]
            session["name"] = user[2]
            session["aadhaar"] = user[1]
            return redirect(url_for("user_dashboard"))
        else:
            flash("Invalid Aadhaar or Password", "error")
            return redirect(url_for("user_login"))
    return render_template("user_login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        aadhaar = request.form.get("aadhaar")
        name = request.form.get("name")
        mobile = request.form.get("mobile")
        password = request.form.get("password")
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (aadhaar, name, mobile, password) VALUES (?, ?, ?, ?)", (aadhaar, name, mobile, password))
            conn.commit()
            flash("Signup successful! Please login.")
        except sqlite3.IntegrityError:
            flash("Aadhaar already exists. Please login.")
        finally:
            conn.close()
        return redirect(url_for("user_login"))
    return render_template("signup.html")

@app.route("/user_dashboard")
def user_dashboard():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
    return render_template("user_dashboard.html", name=session.get("name"), aadhaar=session.get("aadhaar"))

@app.route("/procedure_dashboard", methods=["GET", "POST"])
def procedure_dashboard():
    # ### MODIFIED SECTION ###
    # On a GET request, allow access if either a user or an official is logged in.
    if request.method == "GET":
        if "user_id" not in session and "official_id" not in session:
            flash("You must be logged in to view this page.", "error")
            return redirect(url_for("login_option"))
        # Pass user-specific data if available, otherwise it will be None.
        return render_template("procedure_dashboard.html", 
                               name=session.get("name"), 
                               aadhaar=session.get("aadhaar"))

    # On a POST request, ONLY allow logged-in users to submit.
    if request.method == "POST":
        if "user_id" not in session:
            return jsonify({'success': False, 'message': 'Authentication error. Only users can submit applications.'}), 401
        
        try:
            name = request.form.get("name")
            gram_panchayat = request.form.get("gram_panchayat")
            block = request.form.get("block")
            police_station = request.form.get("police_station")
            district = request.form.get("district")
            state = request.form.get("state")
            latitude = request.form.get("lat")
            longitude = request.form.get("long")
            files = request.files.getlist("evidence_files[]")
            saved_file_paths = []
            if files:
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                for file in files:
                    if file and file.filename != '':
                        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{file.filename}"
                        file_path = os.path.join(UPLOAD_FOLDER, filename)
                        file.save(file_path)
                        saved_file_paths.append(file_path)
            all_paths_str = ",".join(saved_file_paths) if saved_file_paths else None
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute('''INSERT INTO applications (user_id, name, gram_panchayat, block, police_station, district, state, latitude, longitude, datetime, file_path)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (session["user_id"], name, gram_panchayat, block, police_station, district, state, latitude, longitude, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), all_paths_str))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except Exception as e:
            print(f"Error during submission: {e}")
            return jsonify({'success': False, 'message': f'An internal server error occurred: {e}'}), 500

@app.route("/download_application/<int:app_id>")
def download_application(app_id):
    user_id = session.get("user_id")
    official_id = session.get("official_id")
    if not user_id and not official_id:
        return redirect(url_for("login_option"))
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if official_id:
        c.execute("SELECT * FROM applications WHERE id = ?", (app_id,))
    else:
        c.execute("SELECT * FROM applications WHERE id = ? AND user_id = ?", (app_id, user_id))
    app_data = c.fetchone()
    conn.close()
    if not app_data:
        flash("Application not found or you do not have permission to view it.", "error")
        if official_id:
            return redirect(url_for('officials_dashboard'))
        return redirect(url_for('my_applications'))
    pdf = ApplicationPDF()
    pdf.add_page()
    pdf.application_body(dict(app_data))
    pdf_output = pdf.output(dest='S').encode('latin1')
    return Response(pdf_output,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename=application_receipt_{app_id}.pdf'})

@app.route("/my_applications")
def my_applications():
    if "user_id" not in session:
        return redirect(url_for("user_login"))
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM applications WHERE user_id=? ORDER BY id DESC", (session["user_id"],))
    apps = c.fetchall()
    conn.close()
    return render_template("my_applications.html", apps=apps, name=session.get("name"), aadhaar=session.get("aadhaar"))

@app.route('/delete_application/<int:app_id>', methods=['POST'])
def delete_application(app_id):
    if "user_id" not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT file_path FROM applications WHERE id = ? AND user_id = ?", (app_id, session['user_id']))
        application = c.fetchone()
        if not application:
            conn.close()
            return jsonify({'success': False, 'message': 'Application not found or not authorized'}), 404
        file_paths_str = application['file_path']
        if file_paths_str:
            for file_path in file_paths_str.split(','):
                path_to_delete = file_path.strip()
                if os.path.exists(path_to_delete):
                    os.remove(path_to_delete)
        c.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Application deleted successfully.'})
    except Exception as e:
        print(f"Error deleting application {app_id}: {e}")
        return jsonify({'success': False, 'message': 'An internal error occurred.'}), 500

@app.route("/officials_login", methods=["GET", "POST"])
def officials_login():
    if request.method == "POST":
        official_id = request.form.get("official_id")
        password = request.form.get("password")
        if official_id in officials and officials[official_id] == password:
            session["official_id"] = official_id
            return redirect(url_for("officials_dashboard"))
        else:
            flash("Invalid Official ID or Password", "error")
            return redirect(url_for("officials_login"))
    return render_template("officials_login.html")

@app.route("/officials_dashboard")
def officials_dashboard():
    if "official_id" not in session:
        return redirect(url_for("officials_login"))
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM applications ORDER BY id DESC")
    apps = c.fetchall()
    conn.close()
    return render_template("officials_dashboard.html", apps=apps, official_id=session["official_id"])

@app.route('/analyze_application/<int:app_id>', methods=['POST'])
def analyze_application(app_id):
    if "official_id" not in session and "user_id" not in session:
        return jsonify({'success': False, 'message': 'Authentication failed.'}), 401
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT file_path FROM applications WHERE id = ?", (app_id,))
    application = c.fetchone()
    if not application:
        conn.close()
        return jsonify({'success': False, 'message': 'Application not found.'}), 404
    file_paths_str = application['file_path']
    if not file_paths_str:
        conn.close()
        return jsonify({'success': False, 'message': 'No evidence images found for this application.'}), 400
    first_image_path = file_paths_str.split(',')[0].strip()
    if not os.path.exists(first_image_path):
        conn.close()
        return jsonify({'success': False, 'message': 'Image file not found on server.'}), 500
    result = analyze_disaster_image(first_image_path)
    if not result.get('success'):
        conn.close()
        return jsonify({'success': False, 'message': f"AI analysis failed: {result.get('message')}"}), 500
    ai_data = result['data']
    damage = ai_data.get('damage_percentage', 0)
    compensation = ai_data.get('estimated_compensation', 0)
    reasoning = ai_data.get('reasoning', '')
    recommendations = ai_data.get('recommendations', '')
    c.execute('''UPDATE applications SET damage_percentage = ?, compensation_amount = ?, reasoning = ?, recommendations = ?, status = ? WHERE id = ?''',
              (damage, compensation, reasoning, recommendations, 'Reviewed', app_id))
    conn.commit()
    conn.close()
    return jsonify({
        'success': True,
        'damage': f"{damage:.2f}%",
        'compensation': f"₹ {compensation:,.2f}",
        'app_id': app_id
    })

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login_option"))

if __name__ == "__main__":
    init_db()
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)