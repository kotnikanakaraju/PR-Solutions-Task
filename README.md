# AI-Powered Quiz System with FastAPI & PostgreSQL

## Overview
This project is an **AI-driven quiz system** built using **FastAPI** that allows users to:
- **Authenticate** (Register/Login) using OAuth2 with **JWT tokens**.
- **Upload PDFs** containing programming content and generate **AI-based questions** using **Gemini AI**.
- **Answer questions via speech** using **Whisper AI** and **WebSockets**.
- **Evaluate answers** dynamically using **GPT-4 AI** and store scores in **PostgreSQL**.

## Features
✅ **User Authentication** (JWT-based login, token refresh, password hashing with bcrypt)
✅ **PDF Analysis & Question Generation** (Extracts text, generates 10 questions using Gemini AI)
✅ **Speech-to-Text Answering** (WebSockets for real-time interaction, Whisper AI for transcription)
✅ **AI-Based Evaluation** (GPT-4 scores answers dynamically)
✅ **PostgreSQL Integration** (Users, questions, scores stored securely)

## Tech Stack
- **Backend**: FastAPI, Python
- **Database**: PostgreSQL (psycopg2)
- **AI Models**: Gemini AI (Google Generative AI), OpenAI GPT-4, Whisper AI
- **Authentication**: OAuth2, JWT Tokens, bcrypt
- **WebSockets**: Real-time speech-based answer submission

---

## Installation & Setup

### Prerequisites
Ensure you have the following installed:
- Python 3.8+
- PostgreSQL (running locally or via Docker)
- Virtual environment (recommended)

### Clone the Repository
```sh
git clone https://github.com/yourusername/ai-quiz-fastapi.git
cd ai-quiz-fastapi
```

### Create Virtual Environment
```sh
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

### Install Dependencies
```sh
pip install -r requirements.txt
```

### Set Up Environment Variables
Create a `.env` file and configure your API keys and database credentials:
```env
DATABASE_URL=postgresql://your_user:your_password@localhost:5432/your_db
SECRET_KEY=your_secret_key
GEMINI_API_KEY=your_gemini_api_key
OPENAI_API_KEY=your_openai_api_key
```

### Configure PostgreSQL Database
1. **Create Database:**
```sql
CREATE DATABASE your_db;
```
2. **Create Tables:** Run the following SQL in PostgreSQL:
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE scores (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    question_index INTEGER,
    score INTEGER
);
```

---

## Running the Application

### Start the FastAPI Server
```sh
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
The API will be accessible at `http://127.0.0.1:8000`

### API Documentation
FastAPI provides **interactive API docs** at:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## API Endpoints

### Authentication
- **Register**: `POST /register/` (username, password)
- **Login**: `POST /token/` (OAuth2 password flow)
- **Refresh Token**: `POST /refresh_token/`

### PDF Upload & AI Question Generation
- **Upload PDF**: `POST /upload_pdf/` (Generates 10 questions)

### Real-time Voice Answering (WebSocket)
- **Start WebSocket Session**: `ws://127.0.0.1:8000/real_time_answer/`

---

## Contribution
Feel free to contribute! Fork the repo, create a branch, and submit a pull request. 🚀

## License
This project is licensed under the **Apache License**.

## Author
Developed by **Kotni Kanaka Raju** 👨‍💻

---

### 🔥 AI + FastAPI + PostgreSQL = 🚀 Smart Quiz System! 🔥

