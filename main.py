import fitz  # PyMuPDF for PDF Parsing
import openai
import google.generativeai as genai
import whisper
import asyncio
import websockets
import json
import bcrypt
import jwt
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, UploadFile, File, WebSocket, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from tempfile import NamedTemporaryFile
from datetime import datetime, timedelta

# FastAPI App
app = FastAPI()

# Database Connection
conn = psycopg2.connect(
    dbname="quiz_system",
    user="your_user",
    password="your_password",
    host="localhost",
    port="5432",
    cursor_factory=RealDictCursor
)
cur = conn.cursor()

# Security Config
SECRET_KEY = "YOUR_SECRET_KEY"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# AI Model Configs
genai.configure(api_key="YOUR_GEMINI_API_KEY")
openai.api_key = "YOUR_OPENAI_API_KEY"
whisper_model = whisper.load_model("medium")

# ---- Authentication Functions ----
def hash_password(password: str):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(username: str, expires_delta: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)):
    expire = datetime.utcnow() + expires_delta
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ---- User Authentication Endpoints ----
@app.post("/register/")
def register(username: str, password: str):
    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="Username already exists")
    cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hash_password(password)))
    conn.commit()
    return {"message": "User registered successfully"}

@app.post("/token/")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (form_data.username,))
    user = cur.fetchone()
    if not user or not verify_password(form_data.password, user['password_hash']):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    return {"access_token": create_access_token(username=form_data.username), "token_type": "bearer"}

# ---- PDF Analysis ----
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = "\n".join([page.get_text("text") for page in doc])
    doc.close()
    return text

def generate_questions(text):
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(f"Generate 10 questions:\n\n{text}")
    return response.text.split("\n")[:10]

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...), username: str = Depends(get_current_user)):
    with NamedTemporaryFile(delete=True, suffix=".pdf") as temp_file:
        temp_file.write(await file.read())
        temp_file.flush()
        text = extract_text_from_pdf(temp_file.name)
        questions = generate_questions(text)
        for q in questions:
            cur.execute("INSERT INTO questions (user_id, question_text) VALUES ((SELECT id FROM users WHERE username=%s), %s)", (username, q))
        conn.commit()
    return {"questions": questions}

# ---- WebSocket for Real-Time Answering ----
def transcribe_audio(audio_path):
    return whisper_model.transcribe(audio_path)["text"]

def evaluate_response(question, user_answer):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are an AI evaluator."},
                  {"role": "user", "content": f"Question: {question}\nAnswer: {user_answer}\nGive a score (0-10)."}]
    )
    return response["choices"][0]["message"]["content"]

@app.websocket("/real_time_answer/")
async def real_time_answer(websocket: WebSocket, username: str = Depends(get_current_user)):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        request = json.loads(data)
        if "question_index" in request:
            cur.execute("SELECT question_text FROM questions WHERE user_id = (SELECT id FROM users WHERE username=%s) LIMIT 1 OFFSET %s", (username, request["question_index"]))
            question = cur.fetchone()["question_text"]
            await websocket.send_text(json.dumps({"question": question}))
        elif "audio" in request:
            with NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
                temp_audio.write(request["audio"].encode())
                temp_audio.flush()
                transcribed_text = transcribe_audio(temp_audio.name)
            cur.execute("SELECT id, question_text FROM questions WHERE user_id = (SELECT id FROM users WHERE username=%s) LIMIT 1 OFFSET %s", (username, request["question_index"]))
            question_data = cur.fetchone()
            evaluation = evaluate_response(question_data["question_text"], transcribed_text)
            score = int(evaluation.split("Score: ")[1].split("/")[0])
            cur.execute("INSERT INTO scores (user_id, question_id, question_index, transcribed_answer, evaluation, score) VALUES ((SELECT id FROM users WHERE username=%s), %s, %s, %s, %s, %s)", (username, question_data["id"], request["question_index"], transcribed_text, evaluation, score))
            conn.commit()
            await websocket.send_text(json.dumps({"transcribed_answer": transcribed_text, "evaluation": evaluation, "final_score": score}))
