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

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Users table
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    )""")

    # Children table
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
        print("Error: Install opencv-contrib-python")
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
        cur.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                    (data["name"], data["email"], data["password"]))
        conn.commit()
        conn.close()
        return jsonify({"status":"success"})
    except sqlite3.IntegrityError:
        return jsonify({"status":"fail","message":"Email already exists"})

# ---------------- LOGIN ----------------
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=? AND password=?",
                (data["email"], data["password"]))
    user = cur.fetchone()
    conn.close()

    if user:
        return jsonify({"status":"user","email":user[2]})
    return jsonify({"status":"fail"})

# ---------------- REGISTER CHILD ----------------
@app.route("/register_child", methods=["POST"])
def register_child():
    if "photo" not in request.files:
        return jsonify({"message":"No file uploaded"})

    photo = request.files["photo"]
    name = request.form.get("name")
    age = request.form.get("age")
    place = request.form.get("place")

    path = os.path.join(DATASET, photo.filename)
    photo.save(path)

    # Extract face
    img = cv2.imread(path)
    face = extract_face(img)
    if face is None:
        os.remove(path)
        return jsonify({"message":"No face detected"})

    cv2.imwrite(path, face)

    # Save to DB
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO children(name,age,place,image_path) VALUES(?,?,?,?)",
                (name, age, place, path))
    conn.commit()
    conn.close()

    return jsonify({"message":"Child registered"})

# ---------------- GET CHILDREN ----------------
@app.route("/get_children", methods=["GET"])
def get_children():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id,name,age,place FROM children")
    rows = cur.fetchall()
    conn.close()
    return jsonify([{"id":r[0], "name":r[1], "age":r[2], "place":r[3]} for r in rows])

# ---------------- DELETE CHILD ----------------
@app.route("/delete_child/<int:id>", methods=["DELETE"])
def delete_child(id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT image_path FROM children WHERE id=?", (id,))
    row = cur.fetchone()
    if row and os.path.exists(row[0]):
        os.remove(row[0])
    cur.execute("DELETE FROM children WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"message":"Deleted"})

# ---------------- CROSSCHECK IMAGE ----------------
@app.route("/crosscheck", methods=["POST"])
def crosscheck():
    if "photo" not in request.files:
        return jsonify({"status":"no file"})

    photo = request.files["photo"]
    path = os.path.join(UPLOAD_FOLDER, photo.filename)
    photo.save(path)

    img = cv2.imread(path)
    face = extract_face(img)
    os.remove(path)
    if face is None:
        return jsonify({"status":"no face"})

    model = train_model()
    if model is None:
        return jsonify({"status":"no data"})

    label, conf = model.predict(face)
    if conf < 65:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT name, age, place FROM children WHERE id=?",(label,))
        row = cur.fetchone()
        conn.close()
        return jsonify({"status":"found","type":"normal",
                        "name":row[0],"age":row[1],"place":row[2],
                        "confidence":float(conf)})
    else:
        # Reverse age check
        rev_face = reverse_age(face)
        label, conf = model.predict(rev_face)
        if conf < 65:
            conn = sqlite3.connect(DB)
            cur = conn.cursor()
            cur.execute("SELECT name, age, place FROM children WHERE id=?",(label,))
            row = cur.fetchone()
            conn.close()
            return jsonify({"status":"found","type":"reverse_age",
                            "name":row[0],"age":row[1],"place":row[2],
                            "confidence":float(conf)})

    return jsonify({"status":"not found"})

# ---------------- CROSSCHECK VIDEO ----------------
@app.route("/crosscheck_video", methods=["POST"])
def crosscheck_video():
    if "video" not in request.files:
        return jsonify({"status":"no file"})

    video = request.files["video"]
    path = os.path.join(UPLOAD_FOLDER, video.filename)
    video.save(path)

    cap = cv2.VideoCapture(path)
    model = train_model()
    if model is None:
        os.remove(path)
        return jsonify({"status":"no data"})

    frame_count = 0
    found = None

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

        # Normal check
        label, conf = model.predict(face)
        if conf < 65:
            found = {"status":"found","type":"normal","label":label,"confidence":conf}
            break

        # Reverse age check
        rev_face = reverse_age(face)
        label, conf = model.predict(rev_face)
        if conf < 65:
            found = {"status":"found","type":"reverse_age","label":label,"confidence":conf}
            break

    cap.release()
    os.remove(path)

    if found:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT name, age, place FROM children WHERE id=?",(found["label"],))
        row = cur.fetchone()
        conn.close()
        return jsonify({"status":"found","type":found["type"],
                        "name":row[0],"age":row[1],"place":row[2],
                        "confidence":float(found["confidence"])})
    else:
        return jsonify({"status":"not found"})

# ---------------- ROOT ----------------
@app.route("/")
def home():
    return "API Running"

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
