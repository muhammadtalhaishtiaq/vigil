"""
Persistent session storage using JSON files.
Auto-saves on every session mutation. Loads on startup.

Storage location is configurable via VIGIL_DATA_DIR — point it at a mounted
volume (e.g. Railway/Fly persistent disk) so sessions survive redeploys.
Defaults to the project directory.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict
from datetime import datetime

logger = logging.getLogger("session_store")

# cwd, not module dir: works from a repo checkout and a pipx/uvx install alike
_DATA_DIR = Path(os.getenv("VIGIL_DATA_DIR", Path.cwd()))
try:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:  # non-writable mount → fall back to project dir
    logger.warning(f"VIGIL_DATA_DIR unusable ({e}); using project directory")
    _DATA_DIR = Path(__file__).parent

SESSIONS_FILE = _DATA_DIR / "sessions.json"

class SessionStore:
    def __init__(self):
        self.sessions: Dict[str, dict] = {}
        self.load()
    
    def load(self):
        """Load sessions from disk on startup"""
        if not SESSIONS_FILE.exists():
            logger.info("No existing sessions file, starting fresh")
            return
        
        try:
            with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                self.sessions = json.load(f)
            logger.info(f"✅ Loaded {len(self.sessions)} sessions from disk")
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")
            self.sessions = {}
    
    def save(self):
        """Save sessions to disk (atomic write)"""
        try:
            # Write to temp file first
            temp_file = SESSIONS_FILE.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.sessions, f, indent=2, ensure_ascii=False)
            
            # Atomic rename
            temp_file.replace(SESSIONS_FILE)
            logger.debug(f"💾 Saved {len(self.sessions)} sessions to disk")
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")
    
    def get(self, session_id: str) -> dict:
        """Get session by ID"""
        return self.sessions.get(session_id)
    
    def set(self, session_id: str, data: dict):
        """Set session data and auto-save"""
        self.sessions[session_id] = data
        self.save()
    
    def update(self, session_id: str, updates: dict):
        """Update session data (merge) and auto-save"""
        if session_id in self.sessions:
            self.sessions[session_id].update(updates)
            self.save()
    
    def delete(self, session_id: str):
        """Delete session and auto-save"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.save()
    
    def clear_all(self):
        """Clear all sessions"""
        self.sessions = {}
        self.save()
    
    def cleanup_old_sessions(self, max_age_days: int = 7):
        """Remove sessions older than max_age_days"""
        now = datetime.utcnow()
        to_delete = []
        
        for session_id, data in self.sessions.items():
            created_at = data.get("created_at")
            if created_at:
                try:
                    created = datetime.fromisoformat(created_at)
                    age_days = (now - created).days
                    if age_days > max_age_days:
                        to_delete.append(session_id)
                except:
                    pass
        
        for session_id in to_delete:
            del self.sessions[session_id]
        
        if to_delete:
            self.save()
            logger.info(f"🧹 Cleaned up {len(to_delete)} old sessions")

# Global singleton
store = SessionStore()
