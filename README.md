# Django Starter Kit

This Django starter kit is a production-ready template tailored for Iranian projects, providing a modular and scalable foundation for building web applications. It includes robust support for JWT authentication, WebSocket communication, filtering, searching, pagination, REST APIs, Redis caching, and payment gateways optimized for Iranian banks via the `az-iranian-bank-gateways` package. Configurations are centralized in the `config` directory for streamlined management.

## Features

- **Authentication**: JWT-based authentication with custom user model and permissions (`accounts` app).
- **WebSocket Support**: Real-time communication using Django Channels (`notifications` app).
- **REST API**: Built with Django REST Framework, supporting filtering, search, pagination, and OpenAPI schema via `drf-spectacular`.
- **Caching**: Redis integration for high-performance caching (`django-redis`).
- **Audit Logging**: Tracks user actions and system events (`audit_log` app).
- **Notifications**: Real-time notifications via WebSocket (`notifications` app).
- **Payment Integration**: Supports Iranian payment gateways (e.g., SEP, Zarinpal, Mellat) with redirect templates (`payment` app).
- **Feedback System**: Collect and manage user feedback with Celery tasks (`feedback` app).
- **Celery Integration**: Asynchronous task processing with `django-celery-beat` and `django-celery-results`.
- **Sentry Support**: Error tracking and monitoring (`config/sentry.py`).
- **Testing**: Comprehensive test suite using pytest (`tests` directory).
- **Security**: Encrypted model fields, rate limiting, CORS, and secure HTTP headers.
- **Localization**: Persian and English support with `django-mptt` for hierarchical data and `django-countries` for country fields.
- **Debugging**: Tools like `django-debug-toolbar` and `django-silk` for performance monitoring.

## Project Structure

```plaintext
├── accounts/                 # User authentication and management
│   ├── models.py             # Custom User model
│   ├── serializers.py        # API serializers for users
│   ├── views/                # Authentication and user views
│   ├── permissions.py        # Custom permissions
│   └── urls.py               # URL routing
├── audit_log/                # Audit logging for tracking actions
│   ├── middleware.py         # Audit logging middleware
│   ├── models.py             # Audit log models
│   ├── signals.py            # Signal handlers
│   └── utils.py              # Utility functions
├── common/                   # Shared utilities and models
│   ├── models.py             # Shared models
│   ├── serializers.py        # Shared serializers
│   └── utils.py              # Utility functions
├── config/                   # Project configuration
│   ├── asgi.py               # ASGI configuration for Channels
│   ├── celery.py             # Celery configuration
│   ├── sentry.py             # Sentry configuration
│   ├── settings.py           # Django settings
│   └── urls.py               # Root URL configuration
├── feedback/                 # User feedback system
│   ├── models.py             # Feedback models
│   ├── signals.py            # Feedback signals
│   └── tasks.py              # Celery tasks
├── notifications/            # Real-time notifications
│   ├── consumers.py          # WebSocket consumers
│   ├── models.py             # Notification models
│   └── utils.py              # Notification utilities
├── payment/                  # Payment processing for Iranian gateways
│   ├── models.py             # Payment models
│   ├── templates/            # Payment redirect templates
│   └── utils.py              # Payment utilities
├── tests/                    # Test suite
│   ├── test_audit_log.py     # Audit log tests
│   ├── test_auth.py          # Authentication tests
│   ├── test_common_crud.py   # Common CRUD tests
│   └── test_payment_crud.py  # Payment CRUD tests
├── manage.py                 # Django management script
├── pyproject.toml            # Project dependencies
├── pytest.ini                # Pytest configuration
├── static/                   # Static files
└── uv.lock                   # Dependency lock file
```

## Requirements

The project uses Python 3.13+ and includes the following key dependencies (see `pyproject.toml` for the full list):

- `django>=5.2.1`: Core Django framework.
- `djangorestframework>=3.16.0`: REST API framework.
- `djangorestframework-simplejwt>=5.5.0`: JWT authentication.
- `az-iranian-bank-gateways>=2.0.12`: Iranian payment gateways (SEP, Zarinpal, Mellat, etc.).
- `redis[hiredis]>=6.1.0` and `django-redis>=5.4.0`: Redis caching.
- `channels>=4.2.2` and `channels-redis>=4.2.1`: WebSocket support.
- `django-celery-beat>=2.8.1` and `celery>=5.5.2`: Asynchronous task processing.
- `sentry-sdk>=2.28.0`: Error tracking.
- `drf-spectacular>=0.28.0`: API documentation.
- `pytest>=8.3.5` and `pytest-django>=4.11.1`: Testing framework.
- `django-encrypted-model-fields>=0.6.5`: Field encryption.
- `django-mptt>=0.17.0` and `django-countries>=7.6.1`: Hierarchical data and country fields.

## Installation

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/MohammadrezaAmani/django-starter-kit
   cd django-starter-kit
   ```

2. **Set Up Virtual Environment and Install Dependencies**:

   ```bash
   pip install uv
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv sync
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the project root with the following variables:

   ```plaintext
   DJANGO_SECRET_KEY=your-secret-key
   DJANGO_DEBUG=False
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://*.bank.test
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_DB=0
   JWT_SECRET_KEY=your-jwt-secret
   FIELD_ENCRYPTION_KEY=your-encryption-key
   SENTRY_DSN=your-sentry-dsn
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-email-password
   BMI_MERCHANT_CODE=your-bmi-merchant-code
   SEP_MERCHANT_CODE=your-sep-merchant-code
   ZARINPAL_MERCHANT_CODE=your-zarinpal-merchant-code
   IDPAY_MERCHANT_CODE=your-idpay-merchant-code
   ZIBAL_MERCHANT_CODE=your-zibal-merchant-code
   BAHAMTA_MERCHANT_CODE=your-bahamta-merchant-code
   MELLAT_TERMINAL_CODE=your-mellat-terminal-code
   MELLAT_USERNAME=your-mellat-username
   MELLAT_PASSWORD=your-mellat-password
   PAYV1_MERCHANT_CODE=your-payv1-merchant-code
   ```

4. **Run Migrations**:

   ```bash
   uv run manage.py migrate
   ```

5. **Start Redis and Celery**:
   Ensure Redis is running, then start Celery:

   ```bash
   uv run celery -A config.celery worker --loglevel=info
   uv run celery -A config.celery beat --loglevel=info
   ```

6. **Run the Development Server**:
   ```bash
   uv run python manage.py runserver
   ```

## Configuration

Key configurations are defined in `config/settings.py`:

- **Database**: SQLite by default; configure PostgreSQL via `DATABASES` for production.
- **Authentication**: Custom `User` model (`accounts.User`) with JWT (`rest_framework_simplejwt`) and object-level permissions (`django-guardian`).
- **Payment Gateways**: Supports Iranian banks (SEP, BMI, Zarinpal, IDPay, Zibal, Bahamta, Mellat, PayV1) via `az-iranian-bank-gateways`.
- **Caching**: Redis-based caching with `django-redis`.
- **WebSocket**: Redis-backed Channels with `channels-redis`.
- **Security**: CSRF, CORS, rate limiting (`django-ratelimit`), and encrypted fields (`django-encrypted-model-fields`).
- **Localization**: Supports Persian (`fa`) and English (`en`) with timezone set to `Asia/Tehran`.
- **Logging**: File-based logging with Sentry integration for error tracking.
- **API Documentation**: OpenAPI schema with `drf-spectacular` and Swagger UI.

## Usage

- **Authentication**: Use `/v1/accounts/` endpoints for registration, login, and JWT token management.
- **WebSocket Notifications**: Connect to WebSocket endpoints in `notifications/consumers.py`.
- **API**: Access REST API endpoints with filtering, search, and pagination at `/v1/`.
- **Payments**: Process payments via Iranian gateways using `/v1/payment/` endpoints.
- **Feedback**: Collect feedback via `/v1/feedback/` endpoints.
- **Audit Logging**: Automatically logs actions via `audit_log.middleware.AuditLogMiddleware`.

## Testing

Run tests with pytest:

```bash
uv run pytest
```

The `tests` directory includes tests for authentication, audit logging, CRUD operations, and payment processing.

## Debugging

- **Django Debug Toolbar**: Available in debug mode (`DEBUG=True`) for performance insights.
- **Django Silk**: Profiles requests and queries; restricted to superusers in production.

## Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Commit changes (`git commit -m "Add your feature"`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a pull request.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
