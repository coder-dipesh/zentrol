"""
Vercel serverless entry (see `vercel.json`). Re-exports Django's WSGI app.

For local development use `python manage.py runserver` instead.
"""
from config.wsgi import application as app
