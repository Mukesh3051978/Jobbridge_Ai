# JobBridge AI

AI-powered intelligent job portal built with Python, Streamlit, SQLite, and RAG (FAISS + SentenceTransformers).

## Features

- **Authentication**: Secure login/register with bcrypt; roles: Job Seeker, Recruiter, Admin
- **Job Seeker**: Profile, resume upload (PDF parsing), certificates, AI job matches, AI Interview bot, apply for jobs, track application status (My Applications)
- **Resume parsing**: PyMuPDF extraction; skills, education, experience parsed and stored
- **RAG matching**: Embeddings (SentenceTransformers), FAISS vector store; job–candidate similarity and match %
- **AI Interview**: Questions from job description; answer evaluation (rule-based or OpenAI); scores stored
- **Certificate verification**: OCR (Tesseract), issuer/candidate validation, suspicious detection
- **Recruiter**: Post jobs, browse AI-ranked candidates, view full profile (resume, certificates, photo), review AI interview scores, shortlist/reject
- **RAG**: Resume improvement suggestions per job
- **Admin**: Platform stats, users, jobs, interview statistics, skill demand

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Tesseract (optional, for certificate OCR)**

   - Install [Tesseract](https://github.com/tesseract-ocr/tesseract) and ensure it is on PATH, or set `pytesseract.pytesseract.tesseract_cmd` in code.

3. **OpenAI (optional, for LLM interview evaluation)**

   - Set `OPENAI_API_KEY` in the environment to enable LLM-based answer scoring.

4. **Run the app**

   ```bash
   streamlit run app.py
   ```

5. **Deploy (e.g. Streamlit Cloud)**

   - Point the app to `app.py`. Add `packages.txt` if needed for system deps (e.g. tesseract). SQLite and local files work on ephemeral storage; for production use an external DB and object store.

## Project structure

```
jobbridge_ai/
├── app.py                 # Main Streamlit app
├── auth.py                # Login, register, bcrypt, roles
├── database.py            # SQLite schema, connections, profile helpers
├── resume_parser.py       # PDF parsing, skill/education/experience extraction
├── rag_engine.py          # Embeddings, FAISS, job/candidate search
├── interview_bot.py       # Questions, evaluation (LLM/rule-based), session storage
├── certificate_verifier.py # OCR, issuer/name validation
├── recruiter.py           # Job CRUD, candidate listing with filters
├── admin.py               # Analytics, users, jobs, interview stats, skill demand
├── ui_components.py       # CSS, progress bars, toasts
├── requirements.txt
├── uploads/               # Resumes, certificates, photos
└── vector_store/          # FAISS index and metadata
```

## Admin user

Admin registration is disabled in the UI. To create an admin, set role in the database:

```sql
UPDATE users SET role = 'admin' WHERE email = 'your@email.com';
```

## Database

SQLite file: `jobbridge.db`. Tables: `users`, `profiles`, `jobs`, `resumes`, `certificates`, `interview_sessions`, `interview_answers`, `embedding_metadata`, `applications`. Run once; `init_db()` creates tables and folders.
