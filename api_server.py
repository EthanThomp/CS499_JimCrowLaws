#!/usr/bin/env python3
"""
Flask API server for Jim Crow Laws Database
Connects to PostgreSQL database and provides search endpoints
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)  # Enable CORS for frontend communication

# Database connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': os.getenv('POSTGRES_PORT', 5432),
    'database': os.getenv('POSTGRES_DB', 'jimcrow_laws'),
    'user': os.getenv('POSTGRES_USER', 'jimcrow_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'JimCrow@1965')
}

def get_db_connection():
    """Create and return a database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        return None

@app.route('/')
def serve_index():
    """Serve the main HTML file"""
    return send_from_directory('.', 'index.html')

@app.route('/search')
def search_laws():
    """Search laws based on query parameters"""
    try:
        # Get search parameters
        keyword = request.args.get('keyword', '').strip()
        category = request.args.get('category', '').strip()
        year_from = request.args.get('year_from', type=int)
        year_to = request.args.get('year_to', type=int)
        
        # Build the SQL query — only return confirmed Jim Crow laws
        query = """
            SELECT 
                id,
                title,
                year,
                citation,
                category,
                summary,
                keywords,
                full_text AS ocr_text,
                confidence,
                racial_indicator,
                needs_human_review,
                page_number,
                source_file
            FROM legal_documents
            WHERE is_jim_crow = 'yes'
        """
        params = []
        
        # Keyword search across title, summary, and full text
        if keyword:
            query += """ AND (
                title ILIKE %s OR
                summary ILIKE %s OR
                full_text ILIKE %s OR
                array_to_string(keywords, ' ') ILIKE %s
            )"""
            keyword_param = f"%{keyword}%"
            params.extend([keyword_param, keyword_param, keyword_param, keyword_param])
        
        # Category filter
        if category and category != 'all':
            query += " AND category = %s"
            params.append(category)
        
        # Year range filter
        if year_from:
            query += " AND year >= %s"
            params.append(year_from)
        if year_to:
            query += " AND year <= %s"
            params.append(year_to)
        
        query += " ORDER BY year, page_number, id"
        
        # Execute the query
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
        
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(query, params)
            laws = cursor.fetchall()
            
            # Convert to list of dictionaries
            results = []
            for law in laws:
                law_dict = dict(law)
                # Ensure keywords is a list (in case it's stored differently)
                if isinstance(law_dict.get('keywords'), str):
                    # If keywords is stored as a string, convert to list
                    law_dict['keywords'] = [k.strip() for k in law_dict['keywords'].split(',') if k.strip()]
                elif not isinstance(law_dict.get('keywords'), list):
                    law_dict['keywords'] = law_dict.get('keywords', []) or []
                
                results.append(law_dict)
        
        conn.close()
        
        return jsonify({
            "success": True,
            "laws": results,
            "count": len(results)
        })
        
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify({
            "error": "An error occurred while searching",
            "details": str(e)
        }), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            return jsonify({"status": "healthy", "database": "connected"})
        else:
            return jsonify({"status": "unhealthy", "database": "disconnected"}), 500
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Jim Crow Laws API Server...")
    print(f"Database config: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    
    # Test database connection
    conn = get_db_connection()
    if conn:
        print("✓ Database connection successful")
        conn.close()
    else:
        print("✗ Database connection failed - please ensure PostgreSQL is running")
    
    print("Server will run at: http://localhost:5000")
    print("Frontend will be available at: http://localhost:5000/")
    
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)