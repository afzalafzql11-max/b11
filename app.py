from flask import Flask, request, jsonify
from flask_cors import CORS
import os, sqlite3, cv2, numpy as np

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
DATASET = "dataset"
DB = "database.db"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATASET, exist_ok=True)

# ---------------- ADMIN ----------------
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "ths345$"

# ---------------- FACE DETECTOR ----------------
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS children(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        place TEXT,
        image_path TEXT
    )""")

    conn.commit()
    conn.close()

init_db()

# ---------------- FACE EXTRACTION ----------------
def extract_face(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    if len(faces) == 0:
        return None

    x, y, w, h = faces[0]
    face = gray[y:y+h, x:x+w]
    return cv2.resize(face, (200, 200))

# ---------------- REVERSE AGE ----------------
def reverse_age(face):
    smooth = cv2.bilateralFilter(face, 9, 75, 75)
    bright = cv2.convertScaleAbs(smooth, alpha=1.2, beta=10)
    return cv2.equalizeHist(bright)

# ---------------- TRAIN MODEL ----------------
def train_model():
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except:
        return None

    faces, labels = [], []

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, image_path FROM children")
    rows = cur.fetchall()
    conn.close()

    for r in rows:
        img = cv2.imread(r[1], 0)
        if img is None:
            continue

        faces.append(img)
        labels.append(r[0])

        # augmentation
        faces.append(reverse_age(img))
        labels.append(r[0])

    if len(faces) == 0:
        return None

    recognizer.train(faces, np.array(labels))
    return recognizer

# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users(name,email,password) VALUES(?,?,?)",
            (data["name"], data["email"], data["password"])
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "fail", "message": "Email already exists"})

# ---------------- LOGIN ----------------
@app.route("/login", methods=["POST"])
def login():
    data = request.json

    if not data:
        return jsonify({"status": "fail", "message": "No data received"}), 400
    # ADMIN LOGIN
    if data["email"] == ADMIN_EMAIL and data["password"] == ADMIN_PASSWORD:
        return jsonify({"status": "admin", "email": ADMIN_EMAIL})

    # USER LOGIN
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE email=? AND password=?",
        (data["email"], data["password"])
    )
    user = cur.fetchone()
    conn.close()

    if user:
        return jsonify({"status": "user", "email": user[2]})

    return jsonify({"status": "fail"})

# ---------------- REGISTER CHILD ----------------
@app.route("/register_child", methods=["POST"])
def register_child():
    if "photo" not in request.files:
        return jsonify({"message": "No file uploaded"})

    photo = request.files["photo"]
    name = request.form.get("name")
    age = request.form.get("age")
    place = request.form.get("place")

    path = os.path.join(DATASET, photo.filename)
    photo.save(path)

    img = cv2.imread(path)
    face = extract_face(img)

    if face is None:
        os.remove(path)
        return jsonify({"message": "No face detected"})

    cv2.imwrite(path, face)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO children(name,age,place,image_path) VALUES(?,?,?,?)",
        (name, age, place, path)
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Child registered"})

# ---------------- GET CHILDREN ----------------
@app.route("/get_children", methods=["GET"])
def get_children():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id,name,age,place FROM children")
    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {"id": r[0], "name": r[1], "age": r[2], "place": r[3]}
        for r in rows
    ])

# ---------------- ADMIN DELETE ----------------
@app.route("/admin/delete_child/<int:id>", methods=["DELETE"])
def admin_delete_child(id):
    data = request.json

    if not data or data.get("email") != ADMIN_EMAIL or data.get("password") != ADMIN_PASSWORD:
        return jsonify({"status": "unauthorized"}), 403

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT image_path FROM children WHERE id=?", (id,))
    row = cur.fetchone()

    if row and os.path.exists(row[0]):
        os.remove(row[0])

    cur.execute("DELETE FROM children WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return jsonify({"message": "Deleted by admin"})

# ---------------- CROSSCHECK IMAGE ----------------
@app.route("/crosscheck", methods=["POST"])
def crosscheck():
    if "photo" not in request.files:
        return jsonify({"status": "no file"})

    photo = request.files["photo"]
    path = os.path.join(UPLOAD_FOLDER, photo.filename)
    photo.save(path)

    img = cv2.imread(path)
    face = extract_face(img)

    os.remove(path)

    if face is None:
        return jsonify({"status": "no face"})

    model = train_model()
    if model is None:
        return jsonify({"status": "no data"})

    label, conf = model.predict(face)

    if conf < 65:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT name, age, place FROM children WHERE id=?", (label,))
        row = cur.fetchone()
        conn.close()

        return jsonify({
            "status": "found",
            "type": "normal",
            "name": row[0],
            "age": row[1],
            "place": row[2],
            "confidence": float(conf)
        })

    return jsonify({"status": "not found"})

# ---------------- CROSSCHECK VIDEO ----------------
@app.route("/crosscheck_video", methods=["POST"])
def crosscheck_video():
    if "video" not in request.files:
        return jsonify({"status": "no file"})

    video = request.files["video"]
    path = os.path.join(UPLOAD_FOLDER, video.filename)
    video.save(path)

    cap = cv2.VideoCapture(path)
    model = train_model()

    if model is None:
        os.remove(path)
        return jsonify({"status": "no data"})

    found = None
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % 5 != 0:
            continue

        face = extract_face(frame)
        if face is None:
            continue

        label, conf = model.predict(face)
        if conf < 65:
            found = (label, conf, "normal")
            break

        rev_face = reverse_age(face)
        label, conf = model.predict(rev_face)
        if conf < 65:
            found = (label, conf, "reverse_age")
            break

    cap.release()
    os.remove(path)

    if found:
        label, conf, ftype = found

        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT name, age, place FROM children WHERE id=?", (label,))
        row = cur.fetchone()
        conn.close()

        return jsonify({
            "status": "found",
            "type": ftype,
            "name": row[0],
            "age": row[1],
            "place": row[2],
            "confidence": float(conf)
        })

    return jsonify({"status": "not found"})

# ---------------- ROOT ----------------
@app.route("/")
def home():
    return "API Running"

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
