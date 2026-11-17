# Danieli Corus Refractory Laboratory LIMS — Backend

Django REST Framework backend for the Danieli Corus Procedure R-01 Refractory Acceptance & Testing Information Management System (LIMS).

---

## 1. Stack & Architecture

- **Python**: 3.13 / 3.14 compatible
- **Django**: 5.1.15
- **Django REST Framework**: 3.17.2
- **Database**: PostgreSQL 16+ / 18 (`danieli_lims_db`) via `psycopg` 3.3.9
- **Settings & Config**: `django-environ` (Split settings: `base.py`, `development.py`, `production.py`)
- **API Documentation**: OpenAPI 3.0 via `drf-spectacular` (Swagger & Redoc)
- **Testing**: `pytest` & `pytest-django`

---

## 2. Directory Layout

```
Backend LIMS/
├── .venv/                      # Isolated virtual environment
├── .env                        # Local development environment configuration
├── .env.example                # Sanitized template for environment variables
├── .gitignore                  # Git ignore rules for virtual environments, secrets, dumps
├── requirements.txt            # Pinned dependencies
├── pytest.ini                  # Pytest configuration
├── manage.py
├── config/                     # Core project configuration
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py             # Common configurations, DRF defaults, JWT/Session
│   │   ├── development.py      # Local debug & permissive CORS
│   │   └── production.py       # Security headers, SSL redirects, HSTS
│   ├── urls.py                 # Root URL configuration + Swagger/Redoc endpoints
│   ├── views.py                # Public non-sensitive HealthCheckView
│   └── wsgi.py
├── apps/
│   ├── accounts/               # Custom User, Role, OrganizationMembership
│   └── organizations/          # Organization, Facility, LaboratoryArea
└── tests/
    └── test_foundation.py      # Pytest test suite for health & foundational models
```

---

## 3. Quick Start

### 3.1 Environment Activation
```powershell
cd "Backend LIMS"
.\.venv\Scripts\Activate.ps1
```

### 3.2 Environment Variables
Ensure `.env` contains the PostgreSQL connection string:
```bash
SECRET_KEY=danieli-corus-refractory-lims-dev-key-8736428716238712638712638
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,testserver
DATABASE_URL=postgres://postgres:1234@127.0.0.1:5432/danieli_lims_db
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
```

### 3.3 Database Migrations
```powershell
python manage.py showmigrations
python manage.py migrate
```

### 3.4 Running Tests
```powershell
pytest
```

### 3.5 Running Development Server
```powershell
python manage.py runserver 8000
```

---

## 4. Endpoints

- **Health Check**: `GET http://localhost:8000/api/v1/health/`
- **OpenAPI Schema**: `GET http://localhost:8000/api/v1/schema/`
- **Swagger UI**: `GET http://localhost:8000/api/v1/docs/`
- **Redoc UI**: `GET http://localhost:8000/api/v1/redoc/`
- **Admin**: `GET http://localhost:8000/admin/`

---

## 5. Security & RBAC Principles

1. **Custom User Model**: Primary key is UUID. Authentication uses email instead of username.
2. **Decoupled Roles**: Roles are modeled as separate entities (`Role`) assigned through `OrganizationMembership`. Role assignments cannot be injected or changed directly via user payload.
3. **No Hard-Coded Accounts**: Demo accounts and hard-coded passwords from the frontend are eliminated. Real users must be created through admin or seed scripts using standard password hashing.
