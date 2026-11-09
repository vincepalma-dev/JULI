import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# Constants
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_FILE = DATA_DIR / "projects.db"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_connection():
    """Returns a new SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Initializes the database schema."""
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                message_type TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')
        conn.commit()

init_db()

def get_projects() -> List[Dict]:
    """Returns all project metadata."""
    with get_connection() as conn:
        rows = conn.execute('SELECT * FROM projects ORDER BY updated_at DESC').fetchall()
        return [dict(row) for row in rows]

def create_project(name: str) -> Dict:
    """Creates a new project and returns metadata."""
    now = datetime.now().isoformat()
    project_id = str(uuid.uuid4())
    
    project = {
        "id": project_id,
        "name": name,
        "created_at": now,
        "updated_at": now
    }
    
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)',
            (project_id, name, now, now)
        )
        conn.commit()
        
    return project

def get_project(project_id: str) -> Optional[Dict]:
    """Get project metadata along with its full history."""
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
        if not row:
            return None
            
        project = dict(row)
        msg_rows = conn.execute(
            'SELECT agent_name, content, timestamp, message_type FROM messages WHERE project_id = ? ORDER BY id ASC', 
            (project_id,)
        ).fetchall()
        
        project["messages"] = [dict(mr) for mr in msg_rows]
        return project

def delete_project(project_id: str) -> bool:
    """Deletes a project and its history (cascades automatically)."""
    with get_connection() as conn:
        cursor = conn.execute('DELETE FROM projects WHERE id = ?', (project_id,))
        success = cursor.rowcount > 0
        conn.commit()
        return success

def save_message(project_id: str, message: Dict):
    """Appends a message to the project's history."""
    if not project_id:
        return
        
    now = datetime.now().isoformat()
    
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO messages (project_id, agent_name, content, timestamp, message_type) VALUES (?, ?, ?, ?, ?)',
            (
                project_id, 
                message.get('agent_name', ''), 
                message.get('content', ''), 
                message.get('timestamp', now), 
                message.get('message_type', 'agent')
            )
        )
        conn.execute(
            'UPDATE projects SET updated_at = ? WHERE id = ?',
            (now, project_id)
        )
        conn.commit()

def clear_history(project_id: str):
    """Clears history for a project."""
    if not project_id:
        return
        
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute('DELETE FROM messages WHERE project_id = ?', (project_id,))
        conn.execute('UPDATE projects SET updated_at = ? WHERE id = ?', (now, project_id))
        conn.commit()
