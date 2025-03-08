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
from fastapi import FastAPI, UploadFile, File, WebSocket, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from starlette.middleware.sessions import SessionMiddleware
from tempfile import NamedTemporaryFile
from datetime import datetime, timedelta

# FastAPI App
app = FastAPI()

# Database Connection
conn = psycopg2.connect(
    dbname="your_db",
    user="your_user",
    password="your_password",
    host="localhost",
    port="5432"
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

# Store Questions
question_bank = {}

# ---- Authentication ----
def hash_password(password: str):
    """Hashes password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password, hashed_password):
    """Verifies password."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(username: str, expires_delta: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)):
    """Creates an access token with an expiry time."""
    expire = datetime.utcnow() + expires_delta
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(username: str):
    """Creates a refresh token with a longer expiry time."""
    expire = datetime.utcnow() + timedelta(days=7)  # Refresh token valid for 7 days
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    """Gets the current user from JWT token."""
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

# ---- User Authentication ----
@app.post("/register/")
def register(username: str, password: str):
    """Registers a new user."""
    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    hashed_password = hash_password(password)
    cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed_password))
    conn.commit()
    return {"message": "User registered successfully"}

@app.post("/token/")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """User login to get access and refresh tokens."""
    cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (form_data.username,))
    user = cur.fetchone()

    if not user or not verify_password(form_data.password, user[1]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token = create_access_token(username=form_data.username)
    refresh_token = create_refresh_token(username=form_data.username)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@app.post("/refresh_token/")
def refresh_token(refresh_token: str):
    """Generates a new access token using a refresh token."""
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Generate new access token
        new_access_token = create_access_token(username=username)
        return {"access_token": new_access_token, "token_type": "bearer"}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
      
# ---- PDF Analysis & Question Generation ----
def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file."""
    doc = fitz.open(pdf_path)
    text = "\n".join([page.get_text("text") for page in doc])
    doc.close()
    return text

def generate_questions(text):
    """Generates 10 AI-based questions using Gemini AI."""
    prompt = f"Based on the content below, generate 10 questions:\n\n{text}"
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(prompt)
    return response.text.split("\n")[:10]  # Get first 10 questions

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...), username: str = Depends(get_current_user)):
    """Uploads PDF and generates AI-based questions."""
    with NamedTemporaryFile(delete=True, suffix=".pdf") as temp_file:
        temp_file.write(await file.read())
        temp_file.flush()

        text = extract_text_from_pdf(temp_file.name)
        global question_bank
        question_bank[username] = generate_questions(text)

    return {"questions": question_bank[username]}

# ---- Voice Processing WebSocket ----
def transcribe_audio(audio_path):
    """Transcribes speech to text using Whisper AI."""
    result = whisper_model.transcribe(audio_path)
    return result["text"]

def evaluate_response(question, user_answer):
    """Evaluates user's answer using GPT-4 AI scoring (0-10)."""
    prompt = f"Question: {question}\nUser Answer: {user_answer}\nGive a score (0-10) and feedback."
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are an AI evaluator."},
                  {"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

@app.websocket("/real_time_answer/")
async def real_time_answer(websocket: WebSocket, username: str = Depends(get_current_user)):
    """WebSocket for real-time voice-based answering."""
    await websocket.accept()

    while True:
        data = await websocket.receive_text()
        request = json.loads(data)

        if "question_index" in request:
            question_index = request["question_index"]
            question = question_bank[username][question_index]
            await websocket.send_text(json.dumps({"question": question}))

        elif "audio" in request:
            audio_data = request["audio"]
            
            with NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
                temp_audio.write(audio_data)
                temp_audio.flush()

                transcribed_text = transcribe_audio(temp_audio.name)

            evaluation = evaluate_response(question_bank[username][question_index], transcribed_text)

            score = int(evaluation.split("Score: ")[1].split("/")[0])  # Extract score

            cur.execute("INSERT INTO scores (user_id, question_index, score) VALUES ((SELECT id FROM users WHERE username=%s), %s, %s)",
                        (username, question_index, score))
            conn.commit()

            await websocket.send_text(json.dumps({
                "transcribed_answer": transcribed_text,
                "evaluation": evaluation,
                "final_score": score
            }))
