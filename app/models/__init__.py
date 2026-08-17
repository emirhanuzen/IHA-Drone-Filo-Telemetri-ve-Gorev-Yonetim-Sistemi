"""ORM modelleri.

Tüm modeller burada içe aktarılır; böylece Alembic ve SQLAlchemy ilişki
çözümlemesi (relationship) sırasında Base.metadata eksiksiz olur.
"""

from app.models.drone import Drone

__all__ = ["Drone"]
