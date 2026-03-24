# Jim Crow Laws Database — Setup & Usage Guide

This guide covers everything needed to get the project running from scratch: installing dependencies, starting the database, loading data, and accessing the website.

---

## 📋 Prerequisites — What to Download First

Before doing anything else, install these tools:

### 1. Docker Desktop
The database runs inside Docker so you don't need to install PostgreSQL manually.
- Download from: https://www.docker.com/products/docker-desktop
- Install and **launch Docker Desktop** — you must see the whale icon in your system tray before continuing
- Verify it works: open a terminal and run `docker --version`

### 2. Python 3.11 or newer
The API server and data import scripts are written in Python.
- Download from: https://www.python.org/downloads/
- During installation on Windows, **check "Add Python to PATH"**
- Verify: `python --version`

### 3. Git
- Download from: https://git-scm.com/downloads
- Verify: `git --version`

---

## 🗂️ Step 1 — Get the Project Files

Clone the repository and open a terminal inside the project folder:

```bash
git clone <repository-url>
cd CS499_JimCrowLaws
```

You should see these key files:
```
docker-compose.yml       ← Docker database configuration
.env                     ← Database credentials (do not commit this)
init-scripts/            ← SQL that auto-runs when the DB is first created
api_server.py            ← Flask API server (serves the website + handles searches)
import_classified.py     ← Script to load classified laws into the database
index.html               ← The frontend website
doc_processing_results/  ← Classified JSON output from the LLM pipeline
```

---

## 🔑 Step 2 — Configure the Environment File

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Open `.env` and set the values — the defaults below will work for local development:

```env
POSTGRES_DB=jimcrow_laws
POSTGRES_USER=jimcrow_user
POSTGRES_PASSWORD=JimCrow@1965
POSTGRES_PORT=5432

PGADMIN_EMAIL=admin@jimcrow.dev
PGADMIN_PASSWORD=admin123
PGADMIN_PORT=8080

DATABASE_URL=postgresql://jimcrow_user:JimCrow@1965@localhost:5432/jimcrow_laws
```

> ⚠️ The `.env` file is listed in `.gitignore` — never commit it to Git as it contains passwords.

---

## 🐍 Step 3 — Set Up the Python Environment

Create and activate a virtual environment, then install the required packages:

```bash
# Create the virtual environment
python -m venv .venv

# Activate it (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Activate it (Windows Command Prompt)
.venv\Scripts\activate.bat

# Activate it (Mac/Linux)
source .venv/bin/activate
```

Install dependencies:

```bash
pip install flask flask-cors psycopg2-binary python-dotenv
```

---

## 🐘 Step 4 — Start the Database

Make sure Docker Desktop is running, then start the PostgreSQL container:

```bash
docker-compose up -d postgres
```

Wait about 30 seconds for it to initialize, then verify it is healthy:

```bash
docker-compose ps
```

You should see `jimcrow_db` with status **Up (healthy)**.

> The `init-scripts/01-init-database.sql` file runs automatically the **first time** the container starts and creates all the necessary tables.

---

## 📥 Step 5 — Load the Jim Crow Laws Data

With the database running, import the classified law data:

```bash
python import_classified.py
```

This reads from `doc_processing_results/classified_results.json` and inserts **only the entries classified as Jim Crow laws** (`is_jim_crow = "yes"`) into the database. All non-Jim Crow entries are excluded.

You should see output like:

```
Loading: ...\classified_results.json
  Found 24 total entries, 7 classified as Jim Crow laws from: Acts Passed at the Session...
Clearing existing data...
  [01] yes       | Establishment of Common Schools for Colored Children
  [02] yes       | Separate Schools for White and Colored Children
  ...
Done. Inserted 7 entries total.
```

> **Adding new data later:** When new documents are processed through the LLM pipeline and produce a new `_classified.json` file, run:
> ```bash
> python import_classified.py path/to/new_classified.json
> ```
> Note: the script currently clears and reloads all data on each run. If you are loading multiple files, run the import once per file but be aware that each run wipes the previous import — this will be updated as the dataset grows.

---

## 🚀 Step 6 — Start the API Server

This starts the Flask server that serves both the website and the database search API:

```bash
python api_server.py
```

You should see:

```
✓ Database connection successful
Server will run at: http://localhost:5000
 * Running on http://127.0.0.1:5000
```

---

## 🌐 Step 7 — Open the Website

Open your browser and go to:

**http://localhost:5000**

You will see the Jim Crow Laws Database search interface. You can:
- Search by keyword across law titles, text, and summaries
- Filter by category (Education, Marriage, etc.)
- Filter by year range

---

## 🔄 Daily Workflow

Every time you come back to work on the project:

```bash
# 1. Start Docker database
docker-compose up -d postgres

# 2. Activate your Python environment
.venv\Scripts\Activate.ps1      # Windows PowerShell
# or
source .venv/bin/activate        # Mac/Linux

# 3. Start the API server
python api_server.py

# 4. Open browser to http://localhost:5000
```

When you are done:

```bash
# Stop the API server
Ctrl+C

# Stop the database
docker-compose down
```

Your data is saved in a Docker volume and will still be there next time.

---

## 📊 Database Schema

All Jim Crow law records are stored in the `legal_documents` table with these key columns:

| Column | Description |
|--------|-------------|
| `id` | Unique UUID for each record |
| `title` | Law title (generated by LLM) |
| `year` | Year the law was enacted |
| `citation` | Full source citation |
| `category` | Law category (education, marriage, voting, etc.) |
| `summary` | 1–2 sentence LLM-generated summary |
| `keywords` | Array of relevant keywords |
| `full_text` | Original OCR text of the statute |
| `is_jim_crow` | Classification result — always `yes` in this DB |
| `confidence` | LLM confidence score (0.0–1.0) |
| `racial_indicator` | `explicit`, `implicit`, or `none` |
| `needs_human_review` | Flagged for manual review |
| `reasoning` | LLM chain-of-thought explanation |
| `source_file` | Original PDF filename |
| `page_number` | Page number in the source document |

---

## 🔍 Inspecting the Database Directly

You can query the database from the command line at any time:

```bash
# Open a SQL prompt
docker-compose exec postgres psql -U jimcrow_user -d jimcrow_laws

# Useful queries once inside:
SELECT title, year, category FROM legal_documents;   -- list all laws
\d legal_documents                                    -- show table structure
\q                                                    -- quit
```

Or use PgAdmin in the browser at **http://localhost:8080**:
- Email: `admin@jimcrow.dev`
- Password: `admin123`
- Connect to host `postgres`, port `5432`, database `jimcrow_laws`, user `jimcrow_user`

---

## ⚡ Quick Reference

| Task | Command |
|------|---------|
| Start database | `docker-compose up -d postgres` |
| Stop database | `docker-compose down` |
| Check DB status | `docker-compose ps` |
| Load/reload law data | `python import_classified.py` |
| Load a specific file | `python import_classified.py path/to/file.json` |
| Start the web server | `python api_server.py` |
| Open the website | http://localhost:5000 |
| Open PgAdmin | http://localhost:8080 |
| View DB logs | `docker-compose logs postgres` |
| Full reset (⚠️ deletes all data) | `docker-compose down -v` then `docker-compose up -d postgres` |

---

## 🆘 Troubleshooting

### "localhost refused to connect" on http://localhost:5000
The API server is not running. Run `python api_server.py` in your terminal.

### "Error connecting to database" on the website
Either the database container is not running (`docker-compose up -d postgres`) or the API server lost its connection — restart `api_server.py`.

### "Password authentication failed"
Check that your `.env` file has the correct credentials and that the database was started **after** the `.env` file was in place.

### "Port 5432 already in use"
Another PostgreSQL instance is running on your machine. Either stop it, or change `POSTGRES_PORT=5433` in `.env` and restart with `docker-compose down` then `docker-compose up -d postgres`.

### "Port 5000 already in use"
A previous API server process is still running. Find and close it, or restart your terminal.

### Database container won't start
1. Make sure Docker Desktop is open and running
2. Check disk space
3. View logs: `docker-compose logs postgres`
4. Full reset: `docker-compose down -v` then `docker-compose up -d postgres`, then re-run `python import_classified.py`