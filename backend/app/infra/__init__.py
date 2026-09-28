"""Infrastructure: everything the domain refuses to know about.

PDF libraries, OCR, model SDKs, SQLAlchemy, the filesystem. Each module here
implements a port declared in ``domain/ports.py``. Dependencies point inward,
never outward.
"""
