# Flight Schedule Report Extractor

Automated flight schedule reporting system for Citilink.

## Requirements

- Python 3.13+
- MySQL/MariaDB
- Windows/Linux

## Installation

1. **Clone/extract project**
   ```bash
   cd F:\extractor-citilink
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate**
   - Windows: `venv\Scripts\activate`
   - Linux: `source venv/bin/activate`

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure database**
   - Copy `.env.example` to `.env`
   - Edit `.env`:
     ```
     DB_NAME=cilink_report
     DB_USER=root
     DB_PASSWORD=your_mysql_password
     DB_HOST=127.0.0.1
     DB_PORT=3306
     SECRET_KEY=change-in-production
     DEBUG=True
     ```

6. **Create database**
   ```sql
   CREATE DATABASE cilink_report CHARACTER SET utf8mb4;
   ```

7. **Run migrations**
   ```bash
   python manage.py migrate
   ```

8. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

## Run Development Server

```bash
python manage.py runserver
```

Access: `http://localhost:8000/admin`

## Usage

1. **Create Project**
   - Go to Projects → Add
   - Fill: project_id, period (S26), year (2026), month (4)

2. **Upload Files**
   - Go to Source Files → Add
   - Upload WTT PDF, PPRP PDF, GHP Excel
   - Set correct file_type

3. **Process Files**
   - Select uploaded files
   - Actions → "Process selected files"

4. **View Results**
   - Schedule Versions → filter by project
   - Check is_active=True, operational_flag=True

5. **Download Report**
   - Go to Projects
   - Click project row
   - URL: `/admin/core/project/<id>/download/`

## Production Deployment

### On-premise (Windows Server/Linux)

1. **Set production env**
   ```
   DEBUG=False
   SECRET_KEY=strong-random-key-here
   ```

2. **Static files**
   ```bash
   python manage.py collectstatic
   ```

3. **Run with Gunicorn (Linux)**
   ```bash
   pip install gunicorn
   gunicorn config.wsgi:application --bind 0.0.0.0:8000
   ```

4. **Run with waitress (Windows)**
   ```bash
   pip install waitress
   waitress-serve --port=8000 config.wsgi:application
   ```

5. **Reverse proxy (nginx/Apache)**
   - Point to port 8000
   - Serve `/media/` and `/static/` directly

## File Structure

```
extractor-citilink/
├── config/          # Django settings
├── core/            # Main app
│   ├── models.py    # Project, SourceFile, ScheduleVersion
│   ├── admin.py     # Admin UI
│   ├── services.py  # Processing logic
│   ├── analytics.py # Dashboard metrics
│   ├── report.py    # Excel export
│   └── parsers/     # WTT, PPRP, GHP parsers
├── docs/            # Documentation
├── tests/           # Tests
├── manage.py
├── requirements.txt
└── .env
```

## Tests

```bash
python tests/test_parsers.py
```

## Troubleshooting

**MySQL connection error**
- Check `.env` password
- Verify MySQL running: `mysql -u root -p`

**Parser error**
- Check file paths in `docs/Source/`
- Verify PDF/Excel format matches samples

**Import error**
- Activate venv: `venv\Scripts\activate`
- Reinstall: `pip install -r requirements.txt`

## Support

Report issues at project repository.
