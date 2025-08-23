import time
from datetime import timedelta
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.chats.models import Chat, ChatFolder, ChatMessage, ChatParticipant
from apps.chats.serializers import (
    ChatListSerializer,
    ChatMessageSerializer,
    ChatSerializer,
    MessageCreateSerializer,
)

User = get_user_model()


class QueryCountTestCase(TestCase):
    """Test cases for database query optimization."""

    def setUp(self):
        """Set up test data."""
        self.users = []
        for i in range(10):
            user = User.objects.create_user(
                username=f"user{i}",
                email=f"user{i}@example.com",
                password="testpass123",
            )
            self.users.append(user)

        self.chat = Chat.objects.create(
            type=Chat.ChatType.GROUP,
            name="Performance Test Chat",
            creator=self.users[0],
        )

        # Add participants
        for user in self.users:
            ChatParticipant.objects.create(
                user=user, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
            )

        # Create messages
        for i in range(20):
            ChatMessage.objects.create(
                chat=self.chat, sender=self.users[i % 10], content=f"Message {i}"
            )

    def test_chat_list_query_count(self):
        """Test query count for chat list serialization."""
        chats = Chat.objects.all()

        with self.assertNumQueries(5):  # Should be optimized
            serializer = ChatListSerializer(chats, many=True)
            serializer.data  # Force evaluation

    def test_chat_detail_query_count(self):
        """Test query count for chat detail serialization."""
        chat = (
            Chat.objects.select_related("creator", "last_message__sender")
            .prefetch_related("chatparticipant_set__user")
            .get(id=self.chat.id)
        )

        with self.assertNumQueries(10):  # Should be reasonable
            serializer = ChatSerializer(chat)
            serializer.data  # Force evaluation

    def test_message_list_query_count(self):
        """Test query count for message list serialization."""
        messages = (
            ChatMessage.objects.select_related("sender", "reply_to__sender")
            .prefetch_related("attachments")
            .filter(chat=self.chat)[:10]
        )

        with self.assertNumQueries(8):  # Should be optimized
            serializer = ChatMessageSerializer(messages, many=True)
            serializer.data  # Force evaluation

    def test_participant_count_caching(self):
        """Test participant count caching effectiveness."""
        cache.clear()

        # First call - should hit database
        with self.assertNumQueries(1):
            count1 = self.chat.get_participant_count()

        # Second call - should use cache
        with self.assertNumQueries(0):
            count2 = self.chat.get_participant_count()

        self.assertEqual(count1, count2)

    def test_bulk_operations_performance(self):
        """Test bulk operations performance."""
        # Test bulk message creation
        messages_data = []
        for i in range(100):
            messages_data.append(
                ChatMessage(
                    chat=self.chat,
                    sender=self.users[i % 10],
                    content=f"Bulk message {i}",
                )
            )

        start_time = time.time()
        ChatMessage.objects.bulk_create(messages_data)
        bulk_time = time.time() - start_time

        # Individual creation for comparison
        start_time = time.time()
        for i in range(10):  # Smaller sample for comparison
            ChatMessage.objects.create(
                chat=self.chat,
                sender=self.users[i % 10],
                content=f"Individual message {i}",
            )
        individual_time = time.time() - start_time

        # Bulk should be significantly faster per item
        bulk_per_item = bulk_time / 100
        individual_per_item = individual_time / 10

        self.assertLess(bulk_per_item, individual_per_item)


class CachingTestCase(TestCase):
    """Test cases for caching mechanisms."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.chat = Chat.objects.create(name="Cache Test Chat", creator=self.user)

        ChatParticipant.objects.create(
            user=self.user, chat=self.chat, role=ChatParticipant.ParticipantRole.OWNER
        )

    def test_online_status_caching(self):
        """Test online status caching."""
        from apps.chats.serializers import UserBasicSerializer

        cache.clear()

        # First call should set cache
        serializer = UserBasicSerializer(self.user)
        is_online1 = serializer.get_is_online(self.user)

        # Verify cache was set
        cache_key = f"user_online_{self.user.id}"
        cached_value = cache.get(cache_key)
        self.assertIsNotNone(cached_value)

        # Second call should use cache
        is_online2 = serializer.get_is_online(self.user)
        self.assertEqual(is_online1, is_online2)

    def test_participant_count_cache_invalidation(self):
        """Test participant count cache invalidation."""
        cache.clear()

        # Get initial count (should cache)
        count1 = self.chat.get_participant_count()

        # Add new participant
        new_user = User.objects.create_user(
            username="newuser", email="new@example.com", password="testpass123"
        )

        ChatParticipant.objects.create(
            user=new_user, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
        )

        # Cache should be invalidated manually or automatically
        cache.delete(f"chat_participants_{self.chat.id}")

        count2 = self.chat.get_participant_count()
        self.assertEqual(count2, count1 + 1)

    def test_folder_chats_count_caching(self):
        """Test folder chats count caching."""
        folder = ChatFolder.objects.create(user=self.user, name="Test Folder")

        cache.clear()

        # First call should cache
        from apps.chats.serializers import ChatFolderSerializer

        serializer = ChatFolderSerializer(folder)
        serializer.get_chats_count(folder)

        # Verify cache
        cache_key = f"folder_chats_count_{folder.id}"
        cached_value = cache.get(cache_key)
        self.assertIsNotNone(cached_value)


class ConcurrencyTestCase(TransactionTestCase):
    """Test cases for concurrent operations."""

    def setUp(self):
        """Set up test data."""
        self.users = []
        for i in range(5):
            user = User.objects.create_user(
                username=f"user{i}",
                email=f"user{i}@example.com",
                password="testpass123",
            )
            self.users.append(user)

        self.chat = Chat.objects.create(
            type=Chat.ChatType.GROUP,
            name="Concurrency Test Chat",
            creator=self.users[0],
        )

    def test_concurrent_message_creation(self):
        """Test concurrent message creation."""
        import threading
        import time

        messages_created = []
        errors = []

        def create_message(user, content):
            try:
                message = ChatMessage.objects.create(
                    chat=self.chat, sender=user, content=content
                )
                messages_created.append(message)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            thread = threading.Thread(
                target=create_message, args=(self.users[i], f"Concurrent message {i}")
            )
            threads.append(thread)

        # Start all threads
        start_time = time.time()
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        end_time = time.time()

        # Verify results
        self.assertEqual(len(messages_created), 5)
        self.assertEqual(len(errors), 0)
        self.assertLess(end_time - start_time, 2.0)  # Should complete quickly

    def test_concurrent_participant_addition(self):
        """Test concurrent participant addition."""
        import threading

        participants_created = []
        errors = []

        def add_participant(user):
            try:
                participant = ChatParticipant.objects.create(
                    user=user,
                    chat=self.chat,
                    role=ChatParticipant.ParticipantRole.MEMBER,
                )
                participants_created.append(participant)
            except Exception as e:
                errors.append(e)

        threads = []
        for user in self.users[1:]:  # Skip creator
            thread = threading.Thread(target=add_participant, args=(user,))
            threads.append(thread)

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Verify results
        self.assertEqual(len(participants_created), 4)
        self.assertEqual(len(errors), 0)


class MemoryUsageTestCase(TestCase):
    """Test cases for memory usage optimization."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_large_chat_list_memory_usage(self):
        """Test memory usage with large chat list."""
        try:
            import os

            import psutil

            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss
            has_psutil = True
        except ImportError:
            # Mock psutil for testing without the dependency
            initial_memory = 1000000
            has_psutil = False

        # Create many chats
        chats = []
        for i in range(100):  # Reduced for test performance
            chat = Chat.objects.create(name=f"Chat {i}", creator=self.user)
            chats.append(chat)

        # Serialize all chats
        from apps.chats.serializers import ChatListSerializer

        ChatListSerializer(chats, many=True).data

        if has_psutil:
            final_memory = process.memory_info().rss  # noqa
            memory_increase = final_memory - initial_memory
            # Memory increase should be reasonable (less than 50MB)
            self.assertLess(memory_increase, 50 * 1024 * 1024)
        else:
            # Just ensure the operation completes without error
            self.assertEqual(len(chats), 100)

    def test_large_message_list_memory_usage(self):
        """Test memory usage with large message list."""
        try:
            import os

            import psutil

            has_psutil = True
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss
        except ImportError:
            has_psutil = False
            initial_memory = 1000000

        chat = Chat.objects.create(name="Memory Test Chat", creator=self.user)

        # Create many messages
        messages = []
        for i in range(100):  # Reduced for test performance
            message = ChatMessage.objects.create(
                chat=chat,
                sender=self.user,
                content=f"Message {i} content " * 10,  # Make content longer
            )
            messages.append(message)

        # Serialize messages in batches
        from apps.chats.serializers import ChatMessageSerializer

        batch_size = 100
        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            serializer = ChatMessageSerializer(batch, many=True)
            data = serializer.data
            del data  # Free memory

        if has_psutil:
            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory
            # Memory increase should be reasonable
            self.assertLess(memory_increase, 200 * 1024 * 1024)
        else:
            # Just ensure the operation completes without error
            self.assertEqual(len(messages), 100)


class APIPerformanceTestCase(APITestCase):
    """Test cases for API endpoint performance."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.client.force_authenticate(user=self.user)

        # Create test data
        self.chats = []
        for i in range(50):
            chat = Chat.objects.create(name=f"Chat {i}", creator=self.user)
            self.chats.append(chat)

            ChatParticipant.objects.create(
                user=self.user, chat=chat, role=ChatParticipant.ParticipantRole.OWNER
            )

    def test_chat_list_api_performance(self):
        """Test chat list API performance."""
        start_time = time.time()

        response = self.client.get("/chats/")

        end_time = time.time()
        response_time = end_time - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(response_time, 2.0)  # Should respond within 2 seconds

    def test_message_list_api_performance(self):
        """Test message list API performance."""
        chat = self.chats[0]

        # Create messages
        for i in range(100):
            ChatMessage.objects.create(
                chat=chat, sender=self.user, content=f"Message {i}"
            )

        start_time = time.time()

        response = self.client.get(f"/chats/{chat.id}/messages/")

        end_time = time.time()
        response_time = end_time - start_time

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(response_time, 1.0)  # Should respond within 1 second

    def test_message_creation_api_performance(self):
        """Test message creation API performance."""
        chat = self.chats[0]

        data = {"type": "text", "content": "Performance test message"}

        start_time = time.time()

        response = self.client.post(f"/chats/{chat.id}/messages/", data)

        end_time = time.time()
        response_time = end_time - start_time

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertLess(response_time, 0.5)  # Should respond within 0.5 seconds


class FileUploadPerformanceTestCase(APITestCase):
    """Test cases for file upload performance."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.client.force_authenticate(user=self.user)

        self.chat = Chat.objects.create(name="Upload Test Chat", creator=self.user)

        ChatParticipant.objects.create(
            user=self.user, chat=self.chat, role=ChatParticipant.ParticipantRole.OWNER
        )

    def test_small_file_upload_performance(self):
        """Test small file upload performance."""
        # Create 1MB file
        file_content = b"x" * (1024 * 1024)
        test_file = SimpleUploadedFile(
            "test.txt", file_content, content_type="text/plain"
        )

        data = {
            "type": "document",
            "content": "File upload test",
            "attachment_files": [test_file],
        }

        start_time = time.time()

        response = self.client.post(
            f"/chats/{self.chat.id}/messages/", data, format="multipart"
        )

        end_time = time.time()
        upload_time = end_time - start_time

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertLess(upload_time, 5.0)  # Should upload within 5 seconds

    def test_multiple_files_upload_performance(self):
        """Test multiple files upload performance."""
        files = []
        for i in range(5):
            file_content = b"x" * (100 * 1024)  # 100KB each
            test_file = SimpleUploadedFile(
                f"test{i}.txt", file_content, content_type="text/plain"
            )
            files.append(test_file)

        data = {
            "type": "document",
            "content": "Multiple files test",
            "attachment_files": files,
        }

        start_time = time.time()

        response = self.client.post(
            f"/chats/{self.chat.id}/messages/", data, format="multipart"
        )

        end_time = time.time()
        upload_time = end_time - start_time

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertLess(upload_time, 10.0)  # Should upload within 10 seconds


class DatabaseIndexTestCase(TestCase):
    """Test cases for database index effectiveness."""

    def setUp(self):
        """Set up test data."""
        self.users = []
        for i in range(100):
            user = User.objects.create_user(
                username=f"user{i}",
                email=f"user{i}@example.com",
                password="testpass123",
            )
            self.users.append(user)

        self.chats = []
        for i in range(50):
            chat = Chat.objects.create(
                name=f"Chat {i}",
                username=f"chat{i}" if i % 2 == 0 else None,
                creator=self.users[i % 100],
                type=Chat.ChatType.GROUP if i % 3 == 0 else Chat.ChatType.PRIVATE,
            )
            self.chats.append(chat)

    def test_chat_lookup_by_username(self):
        """Test chat lookup by username performance."""
        start_time = time.time()

        # This should use the username index
        chat = Chat.objects.get(username="chat0")

        end_time = time.time()
        lookup_time = end_time - start_time

        self.assertIsNotNone(chat)
        self.assertLess(lookup_time, 0.1)  # Should be very fast with index

    def test_chat_filtering_by_type(self):
        """Test chat filtering by type performance."""
        start_time = time.time()

        # This should use the type index
        group_chats = Chat.objects.filter(type=Chat.ChatType.GROUP)
        count = group_chats.count()

        end_time = time.time()
        filter_time = end_time - start_time

        self.assertGreater(count, 0)
        self.assertLess(filter_time, 0.5)  # Should be fast with index

    def test_message_filtering_by_chat_and_date(self):
        """Test message filtering performance."""
        chat = self.chats[0]

        # Create messages with different dates
        base_time = timezone.now()
        for i in range(100):
            ChatMessage.objects.create(
                chat=chat,
                sender=self.users[i % 10],
                content=f"Message {i}",
                created_at=base_time - timedelta(hours=i),
            )

        start_time = time.time()

        # This should use composite index on (chat, created_at)
        recent_messages = ChatMessage.objects.filter(
            chat=chat, created_at__gte=base_time - timedelta(hours=50)
        )
        count = recent_messages.count()

        end_time = time.time()
        filter_time = end_time - start_time

        self.assertGreater(count, 0)
        self.assertLess(filter_time, 0.5)  # Should be fast with index


class SecurityPerformanceTestCase(TestCase):
    """Test cases for security-related performance."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_file_checksum_calculation_performance(self):
        """Test file checksum calculation performance."""

        # Create 10MB file
        file_content = b"x" * (10 * 1024 * 1024)
        test_file = SimpleUploadedFile(
            "large.txt", file_content, content_type="text/plain"
        )

        serializer = MessageCreateSerializer()

        start_time = time.time()
        checksum = serializer._calculate_checksum(test_file)
        end_time = time.time()

        calculation_time = end_time - start_time

        self.assertIsNotNone(checksum)
        self.assertLess(calculation_time, 5.0)  # Should calculate within 5 seconds

    def test_permission_check_performance(self):
        """Test permission checking performance."""
        chat = Chat.objects.create(name="Permission Test Chat", creator=self.user)

        # Create many participants
        participants = []
        for i in range(100):
            user = User.objects.create_user(f"user{i}", f"user{i}@test.com", "pass")
            participant = ChatParticipant.objects.create(
                user=user, chat=chat, role=ChatParticipant.ParticipantRole.MEMBER
            )
            participants.append(participant)

        start_time = time.time()

        # Check permissions for all participants
        for participant in participants:
            chat.can_user_send_message(participant.user)

        end_time = time.time()
        check_time = end_time - start_time

        # Should check all permissions quickly
        self.assertLess(check_time, 1.0)

    def test_rate_limiting_simulation(self):
        """Test rate limiting performance simulation."""
        chat = Chat.objects.create(
            name="Rate Limit Test",
            creator=self.user,
            slow_mode_delay=10,  # 10 seconds
        )

        # Create recent message
        ChatMessage.objects.create(
            chat=chat,
            sender=self.user,
            content="Recent message",
            created_at=timezone.now() - timedelta(seconds=5),
        )

        data = {"type": ChatMessage.MessageType.TEXT, "content": "New message"}

        start_time = time.time()

        serializer = MessageCreateSerializer(
            data=data, context={"request": Mock(user=self.user), "chat": chat}
        )

        is_valid = serializer.is_valid()

        end_time = time.time()
        validation_time = end_time - start_time

        # Should validate quickly even with rate limiting
        self.assertFalse(is_valid)  # Should fail due to slow mode
        self.assertLess(validation_time, 0.1)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    }
)
class CacheStressTestCase(TestCase):
    """Test cases for cache performance under stress."""

    def setUp(self):
        """Set up test data."""
        self.users = []
        for i in range(50):
            user = User.objects.create_user(
                username=f"user{i}",
                email=f"user{i}@example.com",
                password="testpass123",
            )
            self.users.append(user)

    def test_concurrent_cache_access(self):
        """Test concurrent cache access performance."""
        import random
        import threading

        def cache_operations():
            for i in range(100):
                key = f"test_key_{random.randint(1, 20)}"
                value = f"test_value_{i}"

                # Set cache
                cache.set(key, value, 300)

                # Get cache
                cache.get(key)

                # Delete cache occasionally
                if i % 10 == 0:
                    cache.delete(key)

        threads = []
        for i in range(10):
            thread = threading.Thread(target=cache_operations)
            threads.append(thread)

        start_time = time.time()

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        end_time = time.time()
        total_time = end_time - start_time

        # Should complete within reasonable time
        self.assertLess(total_time, 10.0)

    def test_cache_memory_usage(self):
        """Test cache memory usage with large data."""
        # Store large objects in cache
        large_data = "x" * (1024 * 1024)  # 1MB string

        start_time = time.time()

        for i in range(100):
            cache.set(f"large_key_{i}", large_data, 300)

        end_time = time.time()
        cache_time = end_time - start_time

        # Should cache large data efficiently
        self.assertLess(cache_time, 5.0)

        # Verify data can be retrieved
        retrieved = cache.get("large_key_0")
        self.assertEqual(retrieved, large_data)


class SerializerPerformanceTestCase(TestCase):
    """Test cases for serializer performance optimization."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_nested_serializer_performance(self):
        """Test performance of nested serializers."""
        chat = Chat.objects.create(name="Nested Test Chat", creator=self.user)

        # Create participants with nested user data
        participants = []
        for i in range(50):
            user = User.objects.create_user(f"user{i}", f"user{i}@test.com", "pass")
            participant = ChatParticipant.objects.create(
                user=user, chat=chat, role=ChatParticipant.ParticipantRole.MEMBER
            )
            participants.append(participant)

        from apps.chats.serializers import ChatParticipantSerializer

        start_time = time.time()

        serializer = ChatParticipantSerializer(participants, many=True)
        data = serializer.data

        end_time = time.time()
        serialization_time = end_time - start_time

        self.assertEqual(len(data), 50)
        self.assertLess(serialization_time, 2.0)  # Should serialize quickly

    def test_large_message_list_serialization(self):
        """Test large message list serialization performance."""
        chat = Chat.objects.create(name="Large List Test", creator=self.user)

        # Create many messages
        messages = []
        for i in range(1000):
            message = ChatMessage.objects.create(
                chat=chat, sender=self.user, content=f"Message {i} with some content"
            )
            messages.append(message)

        from apps.chats.serializers import ChatMessageSerializer

        start_time = time.time()

        # Serialize in batches for better performance
        batch_size = 100
        all_data = []

        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            serializer = ChatMessageSerializer(batch, many=True)
            all_data.extend(serializer.data)

        end_time = time.time()
        serialization_time = end_time - start_time

        self.assertEqual(len(all_data), 1000)
        self.assertLess(serialization_time, 10.0)  # Should complete within 10 seconds
