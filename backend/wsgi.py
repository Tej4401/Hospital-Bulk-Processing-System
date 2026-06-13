"""WSGI entrypoint used by gunicorn (``gunicorn wsgi:app``)."""
from app.factory import create_app

app = create_app()

if __name__ == "__main__":
    # Local dev convenience; production uses gunicorn.
    app.run(host="0.0.0.0", port=8080, debug=True)
