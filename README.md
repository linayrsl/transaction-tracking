# Transaction Tracking API

A modern transaction tracking API built with FastAPI, SQLAlchemy, and PostgreSQL.

## Tech Stack

- **FastAPI**: Modern, fast web framework for building APIs
- **SQLAlchemy 2.0**: Async ORM for database operations
- **PostgreSQL 15**: Reliable relational database
- **Alembic**: Database migrations
- **Pydantic**: Data validation and settings management
- **Docker & Docker Compose**: Containerization and orchestration
- **Pytest**: Testing framework
- **Ruff**: Fast Python linter and formatter

## Features

- **Async API**: Built on FastAPI with full async/await support
- **Database ORM**: SQLAlchemy 2.0 with async PostgreSQL support
- **API Versioning**: Versioned API endpoints (/api/v1)
- **Request Logging**: Automatic rotating file logs for all API requests
- **Auto Documentation**: Interactive API docs (Swagger UI and ReDoc)
- **CORS Support**: Configurable CORS middleware
- **Docker Ready**: Full Docker Compose setup for local development

## Prerequisites

- Docker
- Docker Compose

## Quick Start

1. Clone the repository:
```bash
git clone <repository-url>
cd transaction-tracking
```

2. Copy the example environment file:
```bash
cp .env.example .env
```

3. Start the application:
```bash
docker-compose up --build
```

4. Access the API:
- **API**: http://localhost:8000
- **Interactive API Documentation (Swagger UI)**: http://localhost:8000/docs
- **Alternative API Documentation (ReDoc)**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## Development

### Database Migrations

Run all pending migrations:
```bash
docker-compose exec app alembic upgrade head
```

Create a new migration:
```bash
docker-compose exec app alembic revision --autogenerate -m "description of changes"
```

Rollback one migration:
```bash
docker-compose exec app alembic downgrade -1
```

### Running Tests

```bash
docker-compose exec app pytest
docker-compose exec app pytest -v  # verbose output
docker-compose exec app pytest tests/test_specific.py  # specific test file
```

### Code Quality

Format code with Ruff:
```bash
docker-compose exec app ruff format .
```

Lint code with Ruff:
```bash
docker-compose exec app ruff check .
docker-compose exec app ruff check . --fix  # auto-fix issues
```

### Local Development (without Docker)

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables in `.env` file

4. Run the development server:
```bash
uvicorn app.main:app --reload
```

## Project Structure

```
transaction-tracking/
├── app/                    # Application code
│   ├── api/               # API routes
│   │   └── v1/           # API version 1
│   ├── core/             # Core utilities
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── config.py         # Configuration
│   ├── database.py       # Database setup
│   └── main.py           # FastAPI app
├── tests/                 # Test files
├── alembic/              # Database migrations
├── docker-compose.yml    # Docker orchestration
├── Dockerfile            # Docker image
└── pyproject.toml        # Project metadata and dependencies
```

## Request Logging

The API automatically logs all requests to rotating log files in the `logs/` directory.

**View logs:**
```bash
# Inside Docker
docker-compose exec app tail -f logs/api_requests.log

# Local
tail -f logs/api_requests.log
```

**Log format:**
```
[2025-11-25 10:30:45.123] GET /api/v1/transactions - Status: 200 - Query: {"page": "1"} - Body: None - Duration: 45ms
```

**Configuration:**
- Log files rotate when they reach the configured size limit
- Old log files are automatically deleted to save space
- Health check and documentation endpoints are excluded by default
- See `.env.example` for logging configuration options

## Environment Variables

See `.env.example` for all available configuration options:

**Database:**
- `DATABASE_URL`: PostgreSQL connection string

**Application:**
- `PROJECT_NAME`: API project name
- `VERSION`: API version
- `DEBUG`: Enable debug mode
- `ALLOWED_ORIGINS`: CORS allowed origins

**Logging:**
- `LOG_MAX_FILES`: Number of backup log files (default: 5)
- `LOG_MAX_SIZE_MB`: Max size per file in MB (default: 5)
- `LOG_EXCLUDED_PATHS`: Paths to exclude from logging
- `LOG_LEVEL`: Logging level (default: INFO)

## License

[Your License Here]
