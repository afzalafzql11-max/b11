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
    cur.execute("""CREATE TABLE IF NOT EXISTS children(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        place TEXT,
        image_path TEXT)""")
    conn.commit()
    conn.close()

init_db()

# ---------------- FACE EXTRACTION ----------------
def extract_face(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    if len(faces)==0:
        return None
    x,y,w,h = faces[0]
    face = gray[y:y+h, x:x+w]
    return cv2.resize(face, (200,200))

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
        img = cv2.imread(r[1],0)
        if img is None:
            continue
        faces.append(img)
        labels.append(r[0])
        faces.append(reverse_age(img))
        labels.append(r[0])

    if len(faces)==0:
        return None

    recognizer.train(faces, np.array(labels))
    return recognizer

# ---------------- VIDEO CROSSCHECK ----------------
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
        return jsonify({"status":"no data"})

    frame_count = 0
    found = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        # process every 5th frame to speed up
        if frame_count % 5 != 0:
            continue

        face = extract_face(frame)
        if face is None:
            continue

        # NORMAL check
        label, conf = model.predict(face)
        if conf < 65:
            found = {"status":"found","type":"normal","label":label,"confidence":conf}
            break

        # REVERSE AGE check
        rev_face = reverse_age(face)
        label, conf = model.predict(rev_face)
        if conf < 65:
            found = {"status":"found","type":"reverse_age","label":label,"confidence":conf}
            break

    cap.release()
    os.remove(path)  # clean up

    if found:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT name, age, place FROM children WHERE id=?",(found["label"],))
        row = cur.fetchone()
        conn.close()
        return jsonify({
            "status":"found",
            "type":found["type"],
            "name":row[0],
            "age":row[1],
            "place":row[2],
            "confidence":float(found["confidence"])
        })
    else:
        return jsonify({"status":"not found"})
