"""
Shared Flask extension instances.

These are created unbound here (no app yet) and initialized with the real
app in app.py via limiter.init_app(app). Keeping them in their own module
lets auth.py import `limiter` to decorate routes without creating a
circular import with app.py.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate

limiter = Limiter(key_func=get_remote_address)
migrate = Migrate()