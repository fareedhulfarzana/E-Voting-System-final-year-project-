from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify,send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
import cv2
import time
import random
import os
import hashlib
import json
from werkzeug.utils import secure_filename
app = Flask(__name__)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///evoting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'

db = SQLAlchemy(app)

# Email Configuration for OTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-email-password'

mail = Mail(app)

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    
VIDEO_UPLOAD_FOLDER = 'video_records'  # Video recordings
os.makedirs(VIDEO_UPLOAD_FOLDER, exist_ok=True)
app.config['VIDEO_UPLOAD_FOLDER'] = VIDEO_UPLOAD_FOLDER

# Blockchain Storage
BLOCKCHAIN_FILE = "blockchain.json"

# Ensure blockchain file exists
if not os.path.exists(BLOCKCHAIN_FILE):
    with open(BLOCKCHAIN_FILE, "w") as f:
        json.dump([], f)

# Blockchain Structure
class Blockchain:
    def __init__(self):
        self.chain = self.load_blockchain()

    def load_blockchain(self):
        """Load existing blockchain from file"""
        with open(BLOCKCHAIN_FILE, "r") as f:
            return json.load(f)

    def save_blockchain(self):
        """Save blockchain to file"""
        with open(BLOCKCHAIN_FILE, "w") as f:
            json.dump(self.chain, f, indent=4)

    def create_block(self, voter_id, candidate):
        """Create a new block for the vote"""
        previous_hash = self.chain[-1]['hash'] if self.chain else "0"
        vote_data = f"{voter_id}-{candidate}-{time.time()}"
        block_hash = hashlib.sha256(vote_data.encode()).hexdigest()

        block = {
            "index": len(self.chain) + 1,
            "voter_id": voter_id,
            "candidate": candidate,
            "timestamp": time.time(),
            "previous_hash": previous_hash,
            "hash": block_hash,
        }

        self.chain.append(block)
        self.save_blockchain()
        return block

    def verify_integrity(self):
        """Verify blockchain integrity"""
        for i in range(1, len(self.chain)):
            if self.chain[i]['previous_hash'] != self.chain[i - 1]['hash']:
                return False
        return True

blockchain = Blockchain()


# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    voter_id = db.Column(db.String(10), unique=True, nullable=False)
    aadhaar_id = db.Column(db.String(12), unique=True, nullable=False)
    phone_number = db.Column(db.String(15), unique=True, nullable=False)
    otp = db.Column(db.String(6), nullable=True)
    aadhaar_card_path = db.Column(db.String(255), nullable=True)
    voted = db.Column(db.Boolean, default=False)  # ✅ Added to track voting status
    video_path = db.Column(db.String(255), nullable=True)  # ✅ Added to store video path

# Voting Record Model
class VotingRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    voter_id = db.Column(db.String(10), db.ForeignKey('user.voter_id'), nullable=False)  # Foreign Key
    candidate = db.Column(db.String(100), nullable=False)
    video_path = db.Column(db.String(255), nullable=False)  # Store video path
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())  # Store vote time

    user = db.relationship('User', backref=db.backref('voting_records', lazy=True))

@app.route("/vote", methods=["GET"])
def vote():
    if "voter_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    user = User.query.filter_by(voter_id=session["voter_id"]).first()
    
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    if user.voted:
        flash("You have already voted.", "danger")
        return redirect(url_for("dashboard"))

    # Start Timer (5 minutes)
    session["expiry_time"] = time.time() + 300  

    return render_template("voting_page.html", voter_id=session["voter_id"])
    if "voter_id" not in session:
     return redirect(url_for("login"))
     return render_template("voting_page.html")
@app.route("/submit_vote", methods=["POST"])
def submit_vote():
    print("Received a request to submit vote")  # Debugging

    if "video" not in request.files or "candidate" not in request.form:
        print("Missing video or candidate!")  # Debugging
        return jsonify({"error": "Missing video file or candidate selection."}), 400

    video_file = request.files["video"]
    candidate = request.form["candidate"]

    if video_file.filename == "":
        print("Empty video file received!")  # Debugging
        return jsonify({"error": "Empty video file uploaded."}), 400

    if "voter_id" not in session:
        return jsonify({"error": "User not logged in."}), 400

    voter_id = session["voter_id"]  # Get voter ID from session

    # Generate a unique filename (voter_id.mp4)
    video_filename = f"{voter_id}.mp4"
    video_path = os.path.join(app.config['VIDEO_UPLOAD_FOLDER'], video_filename)

    print(f"Saving video to: {video_path}")  # Debugging
    video_file.save(video_path)
    
    # Store vote in blockchain
    blockchain.create_block(voter_id, candidate)
    print(json.dumps(blockchain.chain, indent=4))


    # Store vote in the database
    user = User.query.filter_by(voter_id=voter_id).first()
    if user:
        user.video_path = video_path  # Save video path to User table
        user.voted = True  # Mark user as voted
        new_vote = VotingRecord(voter_id=voter_id, candidate=candidate, video_path=video_path)
        db.session.add(new_vote)
        db.session.commit()

    return jsonify({"message": "Vote submitted successfully!"})
@app.route("/verify_blockchain", methods=["GET"])
def verify_blockchain():
    if blockchain.verify_integrity():
        return jsonify({"message": "Blockchain integrity verified. No tampering detected!"})
    else:
        return jsonify({"error": "Blockchain has been tampered with!"}), 400
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        voter_id = request.form.get("voterId")
        phone_number = request.form.get("phoneNumber")

        user = User.query.filter_by(voter_id=voter_id, phone_number=phone_number).first()

        if not user:
            flash("User not found. Please register first.", "danger")
            return redirect(url_for("register"))

        session["voter_id"] = voter_id
        flash("Login successful! Redirecting to voting page.", "success")
        return redirect(url_for("vote"))  # ✅ Fixed this line
    print("Session voter_id:", session.get("voter_id"))  # Debugging


    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("voter_id", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))

@app.route("/", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        voter_id = request.form.get("voterId", "").strip()
        phone_number = request.form.get("phoneNumber", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        aadhaar_id = request.form.get("aadhaar_id", "").strip()
        aadhaar_card_path = request.form.get("aadhaar_card_path", "").strip()
        

        if not first_name:
            flash("First name is required!", "danger")
            return redirect(url_for("register"))

        if not last_name:
            flash("Last name is required!", "danger")
            return redirect(url_for("register"))

        if "aadhaarCard" not in request.files:
            flash("Please upload your Aadhaar card.", "danger")
            return redirect(url_for("register"))

        aadhaar_card = request.files["aadhaarCard"]
        if aadhaar_card.filename == "":
            flash("No Aadhaar card selected!", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(voter_id=voter_id).first():
            flash("Voter ID already registered. Try logging in.", "danger")
            return redirect(url_for("login"))

        if User.query.filter_by(phone_number=phone_number).first():
            flash("Phone number already registered. Try logging in.", "danger")
            return redirect(url_for("login"))

        # Save Aadhaar Card File
        aadhaar_path = os.path.join(UPLOAD_FOLDER, aadhaar_card.filename)
        aadhaar_card.save(aadhaar_path)

        # Generate OTP
        otp = str(random.randint(100000, 999999))
        session[phone_number] = otp

        # Save new user in database
        new_user = User(
            voter_id=voter_id,
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            aadhaar_id=aadhaar_id,
            aadhaar_card_path=aadhaar_path,
            otp=otp
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! OTP sent to your email.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/send_otp", methods=["POST"])
def send_otp():
    phone_number = request.form.get("phoneNumber")

    if not phone_number:
        return jsonify({"error": "Phone number is required!"}), 400

    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))
    session[phone_number] = otp  # Store OTP in session

    # Print OTP to terminal only (no email)
    print(f"✅ OTP for {phone_number}: {otp}")

    return jsonify({"message": "OTP generated and printed in terminal."})
@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    data = request.json
    phone_number = data.get('phoneNumber')
    otp_entered = data.get('otp')

    # Retrieve the correct OTP from session
    correct_otp = session.get(phone_number)

    if not correct_otp:
        return jsonify({"error": "No OTP found for this phone number. Please request a new OTP."}), 400

    if otp_entered == correct_otp:
        return jsonify({"message": "OTP verified successfully!"}), 200
    else:
        return jsonify({"error": "Invalid OTP. Please try again."}), 400
@app.route("/send_login_otp", methods=["POST"])
def send_login_otp():
    voter_id = request.form.get("voterId")
    phone_number = request.form.get("phoneNumber")

    if not voter_id or not phone_number:
        return jsonify({"error": "Voter ID and Phone Number are required!"}), 400

    # Check if voter ID and phone exist in the database
    user = User.query.filter_by(voter_id=voter_id, phone_number=phone_number).first()
    if not user:
        return jsonify({"error": "User not found. Please register first."}), 400

    # Generate OTP
    otp = str(random.randint(100000, 999999))
    session[phone_number] = otp  # Store OTP in session

    # Print OTP in terminal (for testing)
    print(f"✅ Login OTP for {phone_number}: {otp}")

    return jsonify({"message": "OTP sent. Check your terminal."})


@app.route("/verify_login_otp", methods=["POST"])
def verify_login_otp():
    data = request.json
    phone_number = data.get('phoneNumber')
    otp_entered = data.get('otp')

    # Retrieve the correct OTP from session
    correct_otp = session.get(phone_number)

    if not correct_otp:
        return jsonify({"error": "No OTP found for this phone number. Please request a new OTP."}), 400

    if otp_entered == correct_otp:
        return jsonify({"message": "OTP verified successfully! You can now log in."}), 200
    else:
        return jsonify({"error": "Invalid OTP. Please try again."}), 400
@app.route("/dashboard")
def dashboard():
        return render_template("dashboard.html")
  # Otherwise, go to login page
@app.route("/result")
def result_page():
    # Query database for vote counts, sorting in descending order
    vote_counts = db.session.query(
        VotingRecord.candidate, db.func.count(VotingRecord.candidate)
    ).group_by(VotingRecord.candidate).order_by(db.func.count(VotingRecord.candidate).desc()).all()

    # Convert results to a dictionary (sorted by votes)
    results = {candidate: count for candidate, count in vote_counts}

    # Identify the leading candidate
    leading_candidate = vote_counts[0] if vote_counts else None

    return render_template("result.html", results=results, leading_candidate=leading_candidate)
@app.route('/admins')
def admins_page():
    users = User.query.all()  # Assuming you have a User model in your database
    return render_template("admins.html", users=users)
@app.route('/video_records/<filename>')
def get_video(filename):
    return send_from_directory("static/video_records", filename)
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)