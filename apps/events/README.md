# Events App

A comprehensive event management system built with Django REST Framework that supports conferences, workshops, seminars, and other types of events.

## Features

### Core Functionality
- **Event Management**: Create, update, and manage events with detailed information
- **Session Management**: Organize events into sessions with speakers and schedules
- **Participant Management**: Handle registrations, check-ins, and attendance tracking
- **Exhibitor Support**: Manage sponsors and exhibitors with their products/services
- **Category & Tag System**: Hierarchical categorization and flexible tagging
- **Analytics & Reporting**: Comprehensive event analytics and performance metrics

### Advanced Features
- **Multi-role Support**: Organizers, collaborators, speakers, participants, and exhibitors
- **Permission System**: Fine-grained permissions using Django Guardian
- **Capacity Management**: Event and session capacity limits with waitlists
- **Registration Workflows**: Approval-based and open registration systems
- **Badge System**: Gamification with participant badges and achievements
- **Moderation Tools**: Content moderation and event approval workflows
- **Search & Filtering**: Advanced filtering and search capabilities
- **Favorites System**: Users can favorite events for quick access

## Models

### Core Models

#### Event
Main event model supporting multiple event types:
- **Types**: Conference, Workshop, Seminar, Webinar, Meetup, Training, Hackathon, Competition
- **Status**: Draft, Review, Published, Live, Cancelled, Postponed, Completed
- **Visibility**: Public, Private, Unlisted

#### EventCategory
Hierarchical categories using MPTT:
```python
Technology
├── Web Development
├── Mobile Development
└── AI/ML
```

#### EventTag
Flexible tagging system with usage tracking and trending analysis.

#### Session
Event sessions with:
- Speaker management
- Time scheduling
- Location tracking
- Capacity limits
- Live status

#### Participant
User participation with:
- Multiple roles (Attendee, Speaker, Moderator, Organizer, etc.)
- Registration status tracking
- Attendance management
- Badge system integration

#### Exhibitor
Sponsor and exhibitor management:
- Company information
- Sponsorship tiers
- Product showcases
- Contact management

### Supporting Models

- **EventAnalytics**: Performance metrics and analytics
- **EventAttachment**: File attachments for events
- **EventBadge**: Gamification badges
- **EventFavorite**: User favorites
- **EventView**: View tracking for analytics
- **EventModerationLog**: Moderation action logging
- **Product**: Exhibitor products/services
- **SessionRating**: Session feedback and ratings

## API Endpoints

### Events
```
GET    /v1/events/                 # List events
POST   /v1/events/                 # Create event
GET    /v1/events/{id}/            # Get event details
PUT    /v1/events/{id}/            # Update event
DELETE /v1/events/{id}/            # Delete event

# Event Actions
POST   /v1/events/{id}/register/   # Register for event
POST   /v1/events/{id}/unregister/ # Unregister from event
GET    /v1/events/{id}/sessions/   # Get event sessions
GET    /v1/events/{id}/participants/ # Get participants
POST   /v1/events/{id}/favorite/   # Favorite/unfavorite event
GET    /v1/events/featured/        # Get featured events
GET    /v1/events/trending/        # Get trending events
GET    /v1/events/my_events/       # Get user's events
GET    /v1/events/{id}/analytics/  # Get event analytics
```

### Categories
```
GET    /v1/categories/             # List categories
GET    /v1/categories/{id}/        # Get category details
GET    /v1/categories/{id}/events/ # Get category events
```

### Tags
```
GET    /v1/tags/                   # List tags
GET    /v1/tags/{id}/              # Get tag details
GET    /v1/tags/trending/          # Get trending tags
GET    /v1/tags/{id}/stats/        # Get tag statistics
```

### Sessions
```
GET    /v1/sessions/               # List sessions
POST   /v1/sessions/               # Create session
GET    /v1/sessions/{id}/          # Get session details
PUT    /v1/sessions/{id}/          # Update session
DELETE /v1/sessions/{id}/          # Delete session
POST   /v1/sessions/{id}/rate/     # Rate session
```

### Participants
```
GET    /v1/participants/           # List participants
POST   /v1/participants/           # Register participant
GET    /v1/participants/{id}/      # Get participant details
PUT    /v1/participants/{id}/      # Update participant
DELETE /v1/participants/{id}/      # Remove participant
POST   /v1/participants/{id}/check_in/ # Check in participant
GET    /v1/participants/{id}/badges/   # Get participant badges
```

### Exhibitors
```
GET    /v1/exhibitors/             # List exhibitors
POST   /v1/exhibitors/             # Create exhibitor
GET    /v1/exhibitors/{id}/        # Get exhibitor details
PUT    /v1/exhibitors/{id}/        # Update exhibitor
DELETE /v1/exhibitors/{id}/        # Delete exhibitor
GET    /v1/exhibitors/{id}/products/ # Get exhibitor products
```

### Products
```
GET    /v1/products/               # List products
POST   /v1/products/               # Create product
GET    /v1/products/{id}/          # Get product details
PUT    /v1/products/{id}/          # Update product
DELETE /v1/products/{id}/          # Delete product
```

## Filtering & Search

### Event Filtering
```python
# Filter by categories
GET /v1/events/?categories=1,2,3

# Filter by tags
GET /v1/events/?tags=python,django

# Filter by date range
GET /v1/events/?start_date_after=2024-01-01&start_date_before=2024-12-31

# Filter by price
GET /v1/events/?is_free=true
GET /v1/events/?min_price=0&max_price=100

# Filter by location
GET /v1/events/?location=San Francisco

# Filter by status
GET /v1/events/?status=published,live

# Filter by registration status
GET /v1/events/?registration_open=true
GET /v1/events/?has_capacity=true

# Search
GET /v1/events/?search=python conference
```

### Advanced Filtering
```python
# Multiple filters combined
GET /v1/events/?categories=1&tags=python&is_free=true&registration_open=true

# Ordering
GET /v1/events/?ordering=start_date
GET /v1/events/?ordering=-created_at
```

## Permissions

### Permission Classes
- **IsOwnerOrReadOnly**: Only owners can modify
- **IsEventOrganizerOrCollaborator**: Event organizers and collaborators
- **CanModerateEvent**: Users with moderation permissions

### Object-level Permissions
Using Django Guardian for fine-grained permissions:
- `view_event`: Can view private events
- `change_event`: Can modify event
- `delete_event`: Can delete event
- `moderate_event`: Can moderate event content

### Role-based Access
- **Organizer**: Full control over their events
- **Collaborator**: Can help manage events they're added to
- **Speaker**: Can view and update their sessions
- **Participant**: Can view events they're registered for
- **Exhibitor**: Can manage their booth and products

## Performance Optimizations

### Database Optimizations
- **Select Related**: Optimized queries for foreign keys
- **Prefetch Related**: Optimized queries for many-to-many relationships
- **Database Indexes**: Strategic indexing for common queries
- **Query Optimization**: Minimal database hits per request

### Caching
- **View-level Caching**: Cache expensive views
- **Template Caching**: Cache rendered templates
- **Queryset Caching**: Cache complex querysets

### Pagination
- **Cursor Pagination**: For large datasets
- **Page Pagination**: For smaller datasets with page numbers

## Security Features

### Input Validation
- **Serializer Validation**: Comprehensive input validation
- **File Upload Security**: Secure file handling
- **XSS Protection**: Content sanitization

### Rate Limiting
- **API Rate Limiting**: Prevent API abuse
- **Registration Throttling**: Prevent spam registrations

### Data Privacy
- **Personal Data Protection**: GDPR compliance features
- **Data Anonymization**: User data anonymization options

## Analytics & Reporting

### Event Analytics
- Registration metrics
- Attendance tracking
- Engagement analytics
- Revenue reporting
- Geographic distribution
- Traffic sources

### Performance Metrics
- Popular events
- Trending categories/tags
- User engagement
- Conversion rates

## Testing

### Test Coverage
- **Unit Tests**: Model and utility function tests
- **Integration Tests**: API endpoint tests
- **Performance Tests**: Load and stress testing
- **Security Tests**: Security vulnerability testing

### Test Categories
```
backend/apps/events/tests/
├── test_models.py          # Model tests
├── test_views.py           # API endpoint tests
├── test_serializers.py     # Serializer tests
├── test_permissions.py     # Permission tests
├── test_security.py        # Security tests
└── test_performance.py     # Performance tests
```

## Usage Examples

### Creating an Event
```python
from apps.events.models import Event, EventCategory

# Create event
event = Event.objects.create(
    title="Django Conference 2024",
    description="Annual Django conference",
    organizer=user,
    event_type="conference",
    start_date="2024-06-15T09:00:00Z",
    end_date="2024-06-17T18:00:00Z",
    location="San Francisco, CA",
    max_participants=500,
    registration_fee=299.00
)

# Add categories
tech_category = EventCategory.objects.get(name="Technology")
event.categories.add(tech_category)
```

### Registering for an Event
```python
from apps.events.models import Participant

participant = Participant.objects.create(
    event=event,
    user=user,
    role="attendee",
    registration_data={
        "dietary_restrictions": "Vegetarian",
        "company": "Tech Corp"
    }
)
```

### Creating Sessions
```python
from apps.events.models import Session

session = Session.objects.create(
    event=event,
    title="Building Scalable Django Apps",
    speaker=speaker_user,
    start_time="2024-06-15T10:00:00Z",
    end_time="2024-06-15T11:00:00Z",
    location="Main Hall",
    capacity=200
)
```

## Development Setup

### Requirements
- Django 4.2+
- Django REST Framework 3.14+
- django-guardian (permissions)
- django-mptt (hierarchical categories)
- django-filter (filtering)
- Pillow (image handling)

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create sample data
python manage.py populate_simple_data --users 50

# Run tests
python manage.py test apps.events
```

## Configuration

### Settings
```python
# settings.py
INSTALLED_APPS = [
    'apps.events',
    'guardian',
    'mptt',
    'django_filters',
    'rest_framework',
]

# Guardian settings
GUARDIAN_MONKEY_PATCH = False

# DRF settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}
```

### URL Configuration
```python
# urls.py
urlpatterns = [
    path('api/v1/events/', include('apps.events.urls')),
]
```

## Best Practices

### Event Creation
1. Always validate event dates and capacity
2. Set appropriate permissions for private events
3. Use transactions for complex event creation
4. Implement proper error handling

### Performance
1. Use select_related() for foreign key relationships
2. Use prefetch_related() for many-to-many relationships
3. Implement caching for expensive queries
4. Use pagination for large datasets

### Security
1. Validate all user inputs
2. Use object-level permissions
3. Implement rate limiting
4. Sanitize file uploads

## Monitoring & Maintenance

### Metrics to Monitor
- Event creation rate
- Registration conversion
- API response times
- Database query performance
- Error rates

### Maintenance Tasks
- Clean up expired events
- Archive old data
- Update trending calculations
- Optimize database queries

## Contributing

1. Follow Django coding standards
2. Write tests for new features
3. Update documentation
4. Use meaningful commit messages
5. Create pull requests for review

## License

This project is licensed under the MIT License.
