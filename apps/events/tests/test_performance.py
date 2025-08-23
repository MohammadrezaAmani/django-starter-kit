"""
Performance tests for events app.
"""

import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    Event,
    EventAnalytics,
    EventCategory,
    EventCategoryRelation,
    EventTag,
    EventTagRelation,
    EventView,
    Participant,
    Session,
)

User = get_user_model()


class QueryCountTestCase(TestCase):
    """Test cases for database query optimization."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create categories and tags
        self.categories = []
        for i in range(5):
            category = EventCategory.objects.create(
                name=f"Category {i}", description=f"Description {i}"
            )
            self.categories.append(category)

        self.tags = []
        for i in range(10):
            tag = EventTag.objects.create(
                name=f"Tag {i}", description=f"Description {i}"
            )
            self.tags.append(tag)

        # Create events with relationships
        self.events = []
        for i in range(20):
            event = Event.objects.create(
                title=f"Event {i}",
                description=f"Description {i}",
                organizer=self.user,
                start_date=timezone.now() + timedelta(days=i + 1),
                end_date=timezone.now() + timedelta(days=i + 2),
                status=Event.EventStatus.PUBLISHED,
            )
            self.events.append(event)

            # Add relationships
            EventCategoryRelation.objects.create(
                event=event, category=self.categories[i % len(self.categories)]
            )
            EventTagRelation.objects.create(
                event=event, tag=self.tags[i % len(self.tags)]
            )

            # Create sessions
            for j in range(3):
                Session.objects.create(
                    event=event,
                    title=f"Session {j} for Event {i}",
                    description=f"Session description {j}",
                    start_time=event.start_date + timedelta(hours=j),
                    end_time=event.start_date + timedelta(hours=j + 1),
                )

            # Create participants
            for k in range(5):
                participant_user = User.objects.create_user(
                    username=f"participant_{i}_{k}",
                    email=f"participant_{i}_{k}@example.com",
                    password="testpass123",
                )
                Participant.objects.create(
                    user=participant_user,
                    event=event,
                    registration_status=Participant.RegistrationStatus.CONFIRMED,
                )

    def test_event_list_query_count(self):
        """Test that event list API doesn't generate N+1 queries."""

        # Simulate optimized queryset
        queryset = (
            Event.objects.select_related("organizer")
            .prefetch_related(
                "categories__category",
                "tags__tag",
                "participants",
                "sessions",
            )
            .annotate(participant_count=models.Count("participants"))
        )

        with self.assertNumQueries(6):  # Should be efficient
            list(queryset[:10])  # Evaluate queryset

    def test_event_detail_query_count(self):
        """Test that event detail doesn't cause N+1 queries."""
        event = self.events[0]

        # Optimized query for detail view
        queryset = Event.objects.select_related("organizer").prefetch_related(
            "categories__category",
            "tags__tag",
            "collaborators",
            "sessions__participants__user",
            "participants__user",
        )

        with self.assertNumQueries(5):  # Should be efficient
            event_detail = queryset.get(id=event.id)
            # Access related fields
            list(event_detail.categories.all())
            list(event_detail.tags.all())
            list(event_detail.sessions.all())

    def test_session_list_with_speakers_query_count(self):
        """Test session list with speaker information."""
        event = self.events[0]

        # Create speaker participants
        for session in event.sessions.all()[:2]:
            speaker = User.objects.create_user(
                username=f"speaker_{session.id}",
                email=f"speaker_{session.id}@example.com",
                password="testpass123",
            )
            Participant.objects.create(
                user=speaker,
                event=event,
                role=Participant.Role.SPEAKER,
                registration_status=Participant.RegistrationStatus.CONFIRMED,
            )

        # Optimized query for sessions with speakers
        queryset = (
            Session.objects.filter(event=event)
            .select_related("event")
            .prefetch_related("participants__user")
        )

        with self.assertNumQueries(3):  # Should be efficient
            sessions = list(queryset)
            for session in sessions:
                list(session.participants.all())

    def test_participant_list_query_count(self):
        """Test participant list query optimization."""
        event = self.events[0]

        queryset = (
            Participant.objects.filter(event=event)
            .select_related("user", "event")
            .prefetch_related("badges__badge")
        )

        with self.assertNumQueries(3):  # Should be efficient
            participants = list(queryset)
            for participant in participants:
                participant.user.username  # Should not trigger additional queries


class CachingTestCase(TestCase):
    """Test cases for caching functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

    def tearDown(self):
        cache.clear()

    @override_settings(USE_CACHE=True)
    def test_event_view_caching(self):
        """Test that event views are properly cached."""
        from ..views import EventViewSet

        # First request should hit database
        with self.assertNumQueries(4):  # Initial queries
            viewset = EventViewSet()
            viewset.request = type(
                "MockRequest",
                (),
                {
                    "user": self.user,
                    "META": {"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "test"},
                },
            )()
            viewset.get_object = lambda: self.event
            viewset._track_event_view(self.event, viewset.request)

        # Second request within cache period should not hit database
        with self.assertNumQueries(0):
            viewset._track_event_view(self.event, viewset.request)

    def test_analytics_caching(self):
        """Test that analytics calculations are cached."""
        analytics = EventAnalytics.objects.create(event=self.event)

        # First calculation
        start_time = time.time()
        analytics.recalculate()
        first_duration = time.time() - start_time

        # Second calculation (should be faster due to caching)
        start_time = time.time()
        analytics.recalculate()
        second_duration = time.time() - start_time

        # Second calculation should be faster or equal
        self.assertLessEqual(second_duration, first_duration * 1.1)

    def test_category_event_count_caching(self):
        """Test that category event counts are cached."""
        category = EventCategory.objects.create(
            name="Test Category", description="Test description"
        )

        # Create multiple events in category
        for i in range(5):
            event = Event.objects.create(
                title=f"Event {i}",
                description=f"Description {i}",
                organizer=self.user,
                start_date=timezone.now() + timedelta(days=i + 1),
                end_date=timezone.now() + timedelta(days=i + 2),
                status=Event.EventStatus.PUBLISHED,
            )
            EventCategoryRelation.objects.create(event=event, category=category)

        # Test caching by checking query count
        from ..serializers import EventCategorySerializer

        serializer = EventCategorySerializer(category)

        # First access
        with self.assertNumQueries(1):
            count1 = serializer.get_event_count(category)

        # Add cache attribute to simulate caching
        category.event_count_cache = count1

        # Second access should use cache
        with self.assertNumQueries(0):
            count2 = serializer.get_event_count(category)

        self.assertEqual(count1, count2)


class LoadTestCase(TransactionTestCase):
    """Test cases for load and stress testing."""

    def setUp(self):
        self.users = []
        for i in range(100):
            user = User.objects.create_user(
                username=f"user_{i}",
                email=f"user_{i}@example.com",
                password="testpass123",
            )
            self.users.append(user)

        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password="testpass123"
        )

    def test_bulk_event_creation_performance(self):
        """Test performance of creating multiple events."""
        events_data = []
        for i in range(50):
            events_data.append(
                Event(
                    title=f"Bulk Event {i}",
                    description=f"Description {i}",
                    organizer=self.organizer,
                    start_date=timezone.now() + timedelta(days=i + 1),
                    end_date=timezone.now() + timedelta(days=i + 2),
                    status=Event.EventStatus.PUBLISHED,
                )
            )

        start_time = time.time()
        Event.objects.bulk_create(events_data)
        duration = time.time() - start_time

        # Should create 50 events in less than 1 second
        self.assertLess(duration, 1.0)

    def test_bulk_registration_performance(self):
        """Test performance of bulk user registrations."""
        event = Event.objects.create(
            title="Load Test Event",
            description="Event for load testing",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

        participants_data = []
        for user in self.users:
            participants_data.append(
                Participant(
                    user=user,
                    event=event,
                    registration_status=Participant.RegistrationStatus.CONFIRMED,
                )
            )

        start_time = time.time()
        Participant.objects.bulk_create(participants_data)
        duration = time.time() - start_time

        # Should register 100 users in less than 1 second
        self.assertLess(duration, 1.0)

    def test_concurrent_view_tracking(self):
        """Test performance of concurrent view tracking."""
        event = Event.objects.create(
            title="View Test Event",
            description="Event for view testing",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

        # Simulate concurrent views
        views_data = []
        for i, user in enumerate(self.users[:20]):
            views_data.append(
                EventView(
                    event=event,
                    user=user,
                    ip_address=f"192.168.1.{i + 1}",
                    user_agent="Test Browser",
                )
            )

        start_time = time.time()
        EventView.objects.bulk_create(views_data)
        duration = time.time() - start_time

        # Should track 20 views in less than 0.5 seconds
        self.assertLess(duration, 0.5)


class APIPerformanceTestCase(APITestCase):
    """API performance tests."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create test data
        self.events = []
        for i in range(20):
            event = Event.objects.create(
                title=f"Event {i}",
                description=f"Description {i}",
                organizer=self.user,
                start_date=timezone.now() + timedelta(days=i + 1),
                end_date=timezone.now() + timedelta(days=i + 2),
                status=Event.EventStatus.PUBLISHED,
            )
            self.events.append(event)

    def test_event_list_api_performance(self):
        """Test event list API response time."""
        url = "/v1/events/"

        start_time = time.time()
        response = self.client.get(url)
        duration = time.time() - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should respond in less than 0.5 seconds
        self.assertLess(duration, 0.5)

    def test_event_detail_api_performance(self):
        """Test event detail API response time."""
        event = self.events[0]
        url = f"/v1/events/{event.id}/"

        start_time = time.time()
        response = self.client.get(url)
        duration = time.time() - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should respond in less than 0.3 seconds
        self.assertLess(duration, 0.3)

    def test_event_search_performance(self):
        """Test event search API performance."""
        url = "/v1/events/?search=Event"

        start_time = time.time()
        response = self.client.get(url)
        duration = time.time() - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should respond in less than 0.6 seconds
        self.assertLess(duration, 0.6)

    def test_event_registration_performance(self):
        """Test event registration API performance."""
        self.client.force_authenticate(user=self.user)

        event = self.events[0]
        url = f"/v1/events/{event.id}/register/"

        start_time = time.time()
        response = self.client.post(url)
        duration = time.time() - start_time

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Should respond in less than 0.4 seconds
        self.assertLess(duration, 0.4)

    def test_pagination_performance(self):
        """Test pagination performance with large datasets."""
        # Create more events for pagination testing
        for i in range(100):
            Event.objects.create(
                title=f"Pagination Event {i}",
                description=f"Description {i}",
                organizer=self.user,
                start_date=timezone.now() + timedelta(days=i + 30),
                end_date=timezone.now() + timedelta(days=i + 31),
                status=Event.EventStatus.PUBLISHED,
            )

        # Test first page
        start_time = time.time()
        response = self.client.get("/v1/events/?page=1&page_size=20")
        duration = time.time() - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(duration, 0.5)

        # Test middle page
        start_time = time.time()
        response = self.client.get("/v1/events/?page=3&page_size=20")
        duration = time.time() - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(duration, 0.5)


class MemoryUsageTestCase(TestCase):
    """Test cases for memory usage optimization."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_large_queryset_memory_usage(self):
        """Test memory usage with large querysets."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create large dataset
        events = []
        for i in range(1000):
            events.append(
                Event(
                    title=f"Memory Test Event {i}",
                    description=f"Description {i}",
                    organizer=self.user,
                    start_date=timezone.now() + timedelta(days=i + 1),
                    end_date=timezone.now() + timedelta(days=i + 2),
                    status=Event.EventStatus.PUBLISHED,
                )
            )

        Event.objects.bulk_create(events)

        # Test memory usage with iterator (memory efficient)
        for event in Event.objects.iterator():
            pass

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 50MB)
        self.assertLess(memory_increase, 50 * 1024 * 1024)

    def test_queryset_values_memory_efficiency(self):
        """Test memory efficiency of values() vs full objects."""
        import os

        import psutil

        # Create test data
        for i in range(500):
            Event.objects.create(
                title=f"Values Test Event {i}",
                description=f"Description {i}",
                organizer=self.user,
                start_date=timezone.now() + timedelta(days=i + 1),
                end_date=timezone.now() + timedelta(days=i + 2),
                status=Event.EventStatus.PUBLISHED,
            )

        process = psutil.Process(os.getpid())

        # Test with full objects
        initial_memory = process.memory_info().rss
        events_full = list(Event.objects.all())
        memory_full = process.memory_info().rss - initial_memory

        # Clear reference
        del events_full

        # Test with values only
        initial_memory = process.memory_info().rss
        list(Event.objects.values("id", "title", "start_date"))
        memory_values = process.memory_info().rss - initial_memory

        # Values should use less memory than full objects
        self.assertLess(memory_values, memory_full * 0.8)


class DatabaseIndexTestCase(TestCase):
    """Test cases for database index effectiveness."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create events with various start dates
        for i in range(100):
            Event.objects.create(
                title=f"Index Test Event {i}",
                description=f"Description {i}",
                organizer=self.user,
                start_date=timezone.now() + timedelta(days=i),
                end_date=timezone.now() + timedelta(days=i + 1),
                status=Event.EventStatus.PUBLISHED,
            )

    def test_date_range_query_performance(self):
        """Test performance of date range queries."""
        start_date = timezone.now() + timedelta(days=10)
        end_date = timezone.now() + timedelta(days=50)

        start_time = time.time()
        events = list(
            Event.objects.filter(start_date__gte=start_date, end_date__lte=end_date)
        )
        duration = time.time() - start_time

        # Should be fast due to date indexes
        self.assertLess(duration, 0.1)
        self.assertGreater(len(events), 0)

    def test_status_filter_performance(self):
        """Test performance of status filtering."""
        start_time = time.time()
        published_events = list(
            Event.objects.filter(status=Event.EventStatus.PUBLISHED)
        )
        duration = time.time() - start_time

        # Should be fast due to status index
        self.assertLess(duration, 0.1)
        self.assertGreater(len(published_events), 0)

    def test_organizer_filter_performance(self):
        """Test performance of organizer filtering."""
        start_time = time.time()
        user_events = list(Event.objects.filter(organizer=self.user))
        duration = time.time() - start_time

        # Should be fast due to foreign key index
        self.assertLess(duration, 0.1)
        self.assertEqual(len(user_events), 100)


class ConcurrencyTestCase(TransactionTestCase):
    """Test cases for concurrent access scenarios."""

    def setUp(self):
        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password="testpass123"
        )
        self.event = Event.objects.create(
            title="Concurrency Test Event",
            description="Event for concurrency testing",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            max_participants=10,
            status=Event.EventStatus.PUBLISHED,
        )

    def test_concurrent_registrations(self):
        """Test handling of concurrent registrations."""
        import queue
        import threading

        # Create users for concurrent registration
        users = []
        for i in range(15):  # More users than capacity
            user = User.objects.create_user(
                username=f"concurrent_user_{i}",
                email=f"concurrent_user_{i}@example.com",
                password="testpass123",
            )
            users.append(user)

        results = queue.Queue()

        def register_user(user):
            try:
                participant = Participant.objects.create(
                    user=user,
                    event=self.event,
                    registration_status=Participant.RegistrationStatus.CONFIRMED,
                )
                results.put(("success", participant.id))
            except Exception as e:
                results.put(("error", str(e)))

        # Start concurrent registration threads
        threads = []
        for user in users:
            thread = threading.Thread(target=register_user, args=(user,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Collect results
        successes = 0
        errors = 0
        while not results.empty():
            result_type, _ = results.get()
            if result_type == "success":
                successes += 1
            else:
                errors += 1

        # Should have exactly the capacity number of successes
        self.assertEqual(successes, min(10, 15))  # Capacity limit

        # Verify actual database state
        actual_participants = Participant.objects.filter(event=self.event).count()
        self.assertLessEqual(actual_participants, 10)
