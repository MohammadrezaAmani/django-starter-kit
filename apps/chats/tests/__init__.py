"""
Comprehensive test suite for the chat application.

This module contains all tests for the chat system including:
- Model tests with validation and business logic
- Serializer tests with performance and security checks
- API endpoint tests with authentication and permissions
- WebSocket consumer tests for real-time functionality
- Performance tests for optimization validation
- Security tests for vulnerability assessment
"""

from .test_consumers import *
from .test_models import *
from .test_performance import *
from .test_security import *
from .test_serializers import *
from .test_views import *
