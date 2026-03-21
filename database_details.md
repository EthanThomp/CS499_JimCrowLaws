# PostgreSQL Database Setup Guide

## 🚀 Complete Step-by-Step Setup (5 Minutes)

This guide will help you set up a complete PostgreSQL database for the Jim Crow Laws project using Docker. The database will be ready with all necessary tables and sample data.

### What You'll Get:
- **PostgreSQL 16** database with Jim Crow Laws schema
- **PgAdmin** web interface for easy database management
- **Automatic initialization** with tables and sample data
- **Persistent data** that survives container restarts

### Step 1: Install Prerequisites

**Before starting, make sure you have:**
1. **Docker Desktop** installed and running
   - Download from: https://www.docker.com/products/docker-desktop
   - After installation, make sure Docker Desktop is running (look for whale icon in system tray)
   - **Test Docker:** Open terminal and run `docker --version` - you should see version info
2. **Git** installed (to clone the repository)
3. **VS Code** installed (recommended for viewing database)

### Step 2: Get the Project Files

1. **Make sure you have all project files** including:
   - `docker-compose.yml` (Docker configuration)
   - `.env` (Environment variables with passwords)
   - `init-scripts/01-init-database.sql` (Database schema)
   
2. **Open terminal/command prompt** in the project folder
   - **Windows:** Right-click in the folder → "Open in Terminal" or "Open PowerShell window here"
   - **Mac/Linux:** Open Terminal and `cd` to the project folder

### Step 3: Configure Environment (Optional)

The `.env` file already has working defaults, but you can customize:

```env
POSTGRES_DB=jimcrow_laws
POSTGRES_USER=jimcrow_user
POSTGRES_PASSWORD=JimCrow@1965
POSTGRES_PORT=5432
PGADMIN_EMAIL=admin@jimcrow.dev
PGADMIN_PASSWORD=admin123
PGADMIN_PORT=8080
```

**For production:** Change the passwords to something more secure.

### Step 4: Start the Database System

1. **In your terminal, run this command:**
   ```bash
   docker-compose up -d
   ```

2. **What happens next:**
   - Docker downloads PostgreSQL and PgAdmin images (first time only)
   - Creates and starts both containers
   - Automatically runs the initialization script
   - Sets up the database schema with tables and sample data

3. **Wait about 1-2 minutes** for everything to initialize

4. **Verify it's running:**
   ```bash
   docker-compose ps
   ```
   You should see both `jimcrow_db` and `jimcrow_pgadmin` with status "Up" and "healthy"

### Step 5: Access Your Database

You now have **TWO ways** to access your database:

## 🎯 Method 1: PgAdmin Web Interface (Easiest for Beginners)

1. **Open your web browser** and go to: http://localhost:8080

2. **Login to PgAdmin:**
   - Email: `admin@jimcrow.dev`
   - Password: `admin123`

3. **Connect to your database:**
   - Right-click "Servers" → "Register" → "Server"
   - **General Tab:** Name: `Jim Crow Laws DB`
   - **Connection Tab:**
     - Host: `postgres` (this is the Docker container name)
     - Port: `5432`
     - Database: `jimcrow_laws`
     - Username: `jimcrow_user`
     - Password: `JimCrow@1965`

4. **Explore your database:**
   - Expand the server → Databases → jimcrow_laws → Schemas → public → Tables
   - You'll see: `legal_documents`, `document_classifications`, `extracted_entities`
   - Right-click any table → "View/Edit Data" → "All Rows" to see data

## 🎯 Method 2: VS Code Extensions (Great for Development)

1. **Install PostgreSQL Extension in VS Code:**
   - Open VS Code
   - Click Extensions icon (or press `Ctrl+Shift+X`)
   - Search for "PostgreSQL" 
   - Install the one by "Chris Kolkman"

2. **Connect to Database:**
   - Press `Ctrl+Shift+P` to open Command Palette
   - Type "PostgreSQL: New Connection"
   - Enter these details **exactly**:
     - **Host:** `localhost`
     - **Port:** `5432`
     - **Database:** `jimcrow_laws`
     - **Username:** `jimcrow_user`
     - **Password:** `JimCrow@1965`

3. **View Your Database:**
   - Click the PostgreSQL icon in VS Code sidebar
   - Expand the connection to see your database
   - You can now run SQL queries, view data, and manage tables!

## 🎯 Method 3: Command Line (For Advanced Users)

1. **Access database directly:**
   ```bash
   docker-compose exec postgres psql -U jimcrow_user -d jimcrow_laws
   ```

2. **Try these commands:**
   ```sql
   \l                          -- List all databases
   \d                          -- List all tables
   SELECT * FROM legal_documents;  -- View sample data
   \d legal_documents          -- Show table structure
   \q                          -- Quit
   ```

---

## 📊 Database Schema Overview

Your database includes these main tables:

### `legal_documents`
- Stores the full text and metadata of legal documents
- Includes OCR confidence scores, dates, jurisdiction info
- Full-text search enabled

### `document_classifications`
- Stores AI-powered classifications of documents
- Links to legal_documents with confidence scores
- Tracks which model made each classification

### `extracted_entities`
- Stores extracted entities (people, places, dates, etc.)
- Position information for highlighting in documents
- Confidence scores for each extraction

---

## ⚡ Quick Commands Reference

| Task | Command |
|------|---------|
| **Start database** | `docker-compose up -d` |
| **Stop database** | `docker-compose down` |
| **Check status** | `docker-compose ps` |
| **View logs** | `docker-compose logs postgres` |
| **Access SQL prompt** | `docker-compose exec postgres psql -U jimcrow_user -d jimcrow_laws` |
| **Restart database** | `docker-compose restart postgres` |
| **Remove everything** | `docker-compose down -v` (⚠️ Deletes all data!) |

---

## 🔄 Daily Workflow

**Starting work:**
```bash
docker-compose up -d
```

**Stopping work:**
```bash
docker-compose down
```

**Your data is automatically saved** between sessions!

---

## 🆘 Troubleshooting

### "Can't connect to database"
1. Check Docker Desktop is running (whale icon in system tray)
2. Verify containers are running: `docker-compose ps`
3. If not running: `docker-compose up -d`
4. Check logs: `docker-compose logs postgres`

### "Port already in use" Error
```
Error: port 5432 already in use
```
**Solution:** Either:
1. Stop other PostgreSQL services running on your computer
2. Or change the port in `.env` file: `POSTGRES_PORT=5433`

### "Password authentication failed"
1. Double-check the password in your `.env` file
2. Make sure you're using the exact password when connecting
3. Try restarting: `docker-compose down` then `docker-compose up -d`

### Database won't start
1. Check Docker Desktop is running
2. Check available disk space (Docker needs space)
3. View detailed logs: `docker-compose logs postgres`
4. Try rebuilding: `docker-compose down -v` then `docker-compose up -d`

### PgAdmin won't load
1. Check if PgAdmin container is running: `docker-compose ps`
2. Try accessing: http://localhost:8080
3. Check logs: `docker-compose logs pgadmin`

---

## 👥 For Team Members

**If you're joining this project:**

1. **Get the complete project folder** from your team lead
2. **Make sure you have these files:**
   - `docker-compose.yml`
   - `.env` (with the correct passwords)
   - `init-scripts/01-init-database.sql`
3. **Follow Steps 1-5 above**
4. **You're done!** Everyone has the same database setup

**⚠️ Important Security Notes:**
- Never commit the `.env` file to Git (it contains passwords)
- For production, use stronger passwords
- The `.env` file is already in `.gitignore`

---

## 🚀 Advanced Features

### Adding New Tables
1. Create new `.sql` files in `init-scripts/` folder
2. Name them with numbers: `02-your-new-tables.sql`
3. Restart the database: `docker-compose down -v && docker-compose up -d`

### Backing Up Data
```bash
# Create backup
docker-compose exec postgres pg_dump -U jimcrow_user jimcrow_laws > backup.sql

# Restore backup
docker-compose exec -T postgres psql -U jimcrow_user jimcrow_laws < backup.sql
```

### Connecting Your Python Code
Use this connection string in your Python applications:
```python
DATABASE_URL = "postgresql://jimcrow_user:JimCrow@1965@localhost:5432/jimcrow_laws"
```

---

## 📝 Setup Complete!

If you followed this guide, your database should now be running with:
- ✅ **PostgreSQL 16** container running and healthy
- ✅ **PgAdmin** web interface accessible at http://localhost:8080
- ✅ **Database schema** with 3 tables: `legal_documents`, `document_classifications`, `extracted_entities`
- ✅ **Sample data** inserted for testing
- ✅ **Full-text search** and indexing configured

**Test your setup:**
```bash
docker-compose ps  # Should show both containers as "Up" and "healthy"
```

**Quick verification:**
```bash
# View your sample data
docker-compose exec postgres psql -U jimcrow_user -d jimcrow_laws -c "SELECT title FROM legal_documents;"
```