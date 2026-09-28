"""Entry point.

    cd backend
    python wsgi.py            # http://127.0.0.1:5000/api/health

``flask run`` works too, but this file means one command, one obvious place
to look, and no environment variable to remember (NFR-05).
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
