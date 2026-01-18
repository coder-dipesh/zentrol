# Gesture Presentation System

A Django-based web application for controlling presentations using hand gestures powered by MediaPipe. This application allows users to navigate slides, control presentations, and interact with web content through real-time hand gesture recognition.

## Features

- 🤚 **Real-time Hand Gesture Recognition** - Powered by MediaPipe
- 📊 **Presentation Control** - Navigate slides with gestures
- 📈 **Analytics Dashboard** - Track gesture usage and performance
- 🎯 **Multiple Gesture Support** - Thumbs up, fist, open palm, victory, OK
- 🚀 **Production Ready** - Optimized for deployment on Vercel

## Tech Stack

- **Backend**: Django 4.2, Django REST Framework
- **Frontend**: Vanilla JavaScript, MediaPipe
- **Database**: SQLite (development), PostgreSQL (production recommended)
- **Deployment**: Vercel

## Local Development Setup

### Prerequisites

- Python 3.9+
- pip
- Virtual environment (recommended)

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd gesture-presentation-
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env  # If you have an example file
   # Or create .env file with required variables (see .env file for details)
   ```

5. **Download MediaPipe files (required for offline mode)**
   ```bash
   chmod +x download_mediapipe.sh
   ./download_mediapipe.sh
   ```

6. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

7. **Create superuser (optional, for admin access)**
   ```bash
   python manage.py createsuperuser
   ```

8. **Setup demo data (optional)**
   ```bash
   python manage.py setup_demo
   ```

9. **Run development server**
   ```bash
   python manage.py runserver
   ```

10. **Access the application**
    - Main app: http://localhost:8000
    - Admin panel: http://localhost:8000/admin

## Production Deployment on Vercel

### Prerequisites

- Vercel account (free tier available)
- Git repository (GitHub, GitLab, or Bitbucket)
- Production database (recommended: Vercel Postgres, Neon, or Supabase)

### Deployment Steps

1. **Push your code to a Git repository**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **Import project to Vercel**
   - Go to [Vercel Dashboard](https://vercel.com/dashboard)
   - Click "Add New Project"
   - Import your Git repository
   - Vercel will auto-detect Django settings

3. **Configure environment variables in Vercel**
   
   In Vercel Dashboard → Project Settings → Environment Variables, add:
   
   **Required:**
   ```
   SECRET_KEY=<generate-a-new-secret-key>
   DEBUG=False
   ALLOWED_HOSTS=your-app.vercel.app,www.your-domain.com
   ```
   
   **Database (if using PostgreSQL):**
   ```
   DATABASE_URL=postgresql://user:password@host:port/database
   ```
   
   **CORS & CSRF:**
   ```
   CORS_ALLOWED_ORIGINS=https://your-app.vercel.app,https://www.your-domain.com
   CSRF_TRUSTED_ORIGINS=https://your-app.vercel.app,https://www.your-domain.com
   ```
   
   **Optional:**
   ```
   LOG_LEVEL=INFO
   SECURE_SSL_REDIRECT=True
   SESSION_COOKIE_SECURE=True
   CSRF_COOKIE_SECURE=True
   ```

4. **Generate a new SECRET_KEY for production**
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
   Copy the output and use it as `SECRET_KEY` in Vercel.

5. **Configure Build Settings**
   
   In Vercel Dashboard → Project Settings → Build & Development Settings:
   - **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - **Output Directory**: Leave empty (or set to `staticfiles` if needed)
   - **Install Command**: (leave empty, handled in build command)

6. **Run migrations on first deployment**
   
   You may need to run migrations manually:
   ```bash
   # Using Vercel CLI
   vercel env pull
   python manage.py migrate
   ```
   
   Or use a build script that includes migrations (not recommended for production):
   ```bash
   # Add to build command (only for first deployment):
   python manage.py migrate --noinput
   ```

7. **Deploy**
   - Vercel will automatically deploy on every push to your main branch
   - Or click "Deploy" in the dashboard

### Post-Deployment

1. **Create superuser** (via Vercel CLI or database directly)
2. **Verify static files** are being served correctly
3. **Test all routes** and functionality
4. **Set up custom domain** (optional) in Vercel dashboard

### Troubleshooting

**Static files not loading:**
- Ensure `whitenoise` is in `requirements.txt`
- Verify `STATIC_ROOT` is set correctly in settings
- Check that `collectstatic` runs during build
- Verify static files are in `staticfiles/` directory

**Database errors:**
- Ensure `DATABASE_URL` is set correctly in Vercel environment variables
- Run migrations after first deployment
- For SQLite: Note that SQLite may not work well on Vercel's serverless environment

**CORS errors:**
- Update `CORS_ALLOWED_ORIGINS` with your Vercel domain
- Update `CSRF_TRUSTED_ORIGINS` with your domain

**Debugging:**
- Check Vercel logs in the dashboard
- Enable verbose logging by setting `LOG_LEVEL=DEBUG` temporarily
- Use Vercel CLI: `vercel logs`

## Project Structure

```
gesture-presentation-/
├── config/              # Django project settings
│   ├── settings.py      # Main settings file
│   ├── urls.py          # URL configuration
│   ├── wsgi.py          # WSGI entry point for production
│   └── asgi.py          # ASGI entry point (for future WebSocket support)
├── gestures/            # Main application
│   ├── models.py        # Database models
│   ├── views.py         # View logic
│   ├── urls.py          # URL routing
│   └── serializers.py   # DRF serializers
├── analytics/           # Analytics app
├── static/              # Static files (CSS, JS, images)
│   ├── css/
│   ├── js/
│   └── media/
├── templates/           # HTML templates
├── requirements.txt     # Python dependencies
├── vercel.json          # Vercel configuration
├── .env                 # Environment variables (not in git)
└── manage.py            # Django management script
```

## Environment Variables

See `.env` file for all available environment variables and their descriptions.

**Key variables:**
- `SECRET_KEY` - Django secret key (required)
- `DEBUG` - Debug mode (False in production)
- `ALLOWED_HOSTS` - Comma-separated list of allowed hosts
- `DATABASE_URL` - Database connection string
- `CORS_ALLOWED_ORIGINS` - CORS allowed origins
- `CSRF_TRUSTED_ORIGINS` - CSRF trusted origins

## API Endpoints

- `GET /` - Home page
- `GET /presentation/` - Presentation interface
- `POST /api/log-gesture/` - Log gesture detection
- `GET /api/gesture-logs/` - List gesture logs (API)
- `GET /admin/` - Django admin panel

## Development

### Running Tests
```bash
pytest
# or
python manage.py test
```

### Code Formatting
```bash
black .
flake8 .
```

### Making Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

## License

[Your License Here]

## Support

For issues and questions, please open an issue on the repository.

