"""Ortak FastAPI bağımlılıkları.

Veritabanı oturumu buradan yeniden dışa aktarılır; ileride kimlik doğrulama
bağımlılıkları (get_current_user, rol kontrolü) da bu modülde toplanacak.
"""

from app.db.database import get_db

__all__ = ["get_db"]
