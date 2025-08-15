import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from .models import Event, EventView, Participant, Session

logger = logging.getLogger(__name__)
User = get_user_model()


class EventConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time event updates.

    Handles:
    - Live event updates (status changes, announcements)
    - Session updates (start/end, speaker changes)
    - Attendance tracking
    - Real-time messaging and notifications
    - Live polls and Q&A
    - Networking connections
    """

    async def connect(self):
        self.event_id = self.scope["url_route"]["kwargs"]["event_id"]
        self.event_group_name = f"event_{self.event_id}"
        self.user = self.scope["user"]

        # Verify user has access to this event
        if not await self.user_can_access_event():
            await self.close()
            return

        # Join event group
        await self.channel_layer.group_add(self.event_group_name, self.channel_name)

        await self.accept()

        # Send initial event data
        await self.send_event_data()

        # Track user connection
        await self.track_user_connection()

        logger.info(f"User {self.user} connected to event {self.event_id}")

    async def disconnect(self, close_code):
        # Leave event group
        await self.channel_layer.group_discard(self.event_group_name, self.channel_name)

        # Track user disconnection
        await self.track_user_disconnection()

        logger.info(f"User {self.user} disconnected from event {self.event_id}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "ping":
                await self.send_json({"type": "pong"})

            elif message_type == "join_session":
                await self.handle_join_session(data)

            elif message_type == "leave_session":
                await self.handle_leave_session(data)

            elif message_type == "update_location":
                await self.handle_location_update(data)

            elif message_type == "poll_response":
                await self.handle_poll_response(data)

            elif message_type == "qa_question":
                await self.handle_qa_question(data)

            elif message_type == "networking_request":
                await self.handle_networking_request(data)

            elif message_type == "chat_message":
                await self.handle_chat_message(data)

            else:
                logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self.send_error("Internal error")

    async def send_json(self, data):
        """Send JSON data to WebSocket."""
        await self.send(text_data=json.dumps(data))

    async def send_error(self, message):
        """Send error message to client."""
        await self.send_json({"type": "error", "message": message})

    # Event handlers for group messages
    async def event_update(self, event):
        """Send event update to client."""
        await self.send_json({"type": "event_update", "data": event["data"]})

    async def session_update(self, event):
        """Send session update to client."""
        await self.send_json({"type": "session_update", "data": event["data"]})

    async def attendance_update(self, event):
        """Send attendance update to client."""
        await self.send_json({"type": "attendance_update", "data": event["data"]})

    async def notification(self, event):
        """Send notification to client."""
        await self.send_json({"type": "notification", "data": event["data"]})

    async def poll_update(self, event):
        """Send poll update to client."""
        await self.send_json({"type": "poll_update", "data": event["data"]})

    async def qa_update(self, event):
        """Send Q&A update to client."""
        await self.send_json({"type": "qa_update", "data": event["data"]})

    async def networking_update(self, event):
        """Send networking update to client."""
        await self.send_json({"type": "networking_update", "data": event["data"]})

    async def chat_message(self, event):
        """Send chat message to client."""
        await self.send_json({"type": "chat_message", "data": event["data"]})

    # Helper methods
    @database_sync_to_async
    def user_can_access_event(self):
        """Check if user can access this event."""
        try:
            if not self.user.is_authenticated:
                return False

            event = Event.objects.get(id=self.event_id)

            # Check visibility
            if event.visibility == Event.Visibility.PUBLIC:
                return True
            elif event.visibility == Event.Visibility.PRIVATE:
                return (
                    event.organizer == self.user
                    or self.user in event.co_organizers.all()
                    or self.user in event.moderators.all()
                    or self.user.has_perm("events.view_event", event)
                )
            elif event.visibility == Event.Visibility.INVITE_ONLY:
                return Participant.objects.filter(user=self.user, event=event).exists()

            return False

        except Event.DoesNotExist:
            return False

    @database_sync_to_async
    def get_event_data(self):
        """Get current event data."""
        try:
            event = Event.objects.select_related("organizer").get(id=self.event_id)
            return {
                "id": str(event.id),
                "name": event.name,
                "status": event.status,
                "start_date": event.start_date.isoformat(),
                "end_date": event.end_date.isoformat(),
                "is_live": event.is_live,
                "registration_count": event.registration_count,
                "attendance_count": event.attendance_count,
            }
        except Event.DoesNotExist:
            return None

    async def send_event_data(self):
        """Send initial event data to client."""
        event_data = await self.get_event_data()
        if event_data:
            await self.send_json({"type": "event_data", "data": event_data})

    @database_sync_to_async
    def track_user_connection(self):
        """Track user connection for analytics."""
        if self.user.is_authenticated:
            try:
                event = Event.objects.get(id=self.event_id)
                EventView.objects.create(
                    event=event,
                    user=self.user,
                    ip_address=self.scope.get("client", [""])[0],
                    user_agent=dict(self.scope.get("headers", {}))
                    .get(b"user-agent", b"")
                    .decode(),
                )
            except Exception as e:
                logger.error(f"Error tracking connection: {e}")

    @database_sync_to_async
    def track_user_disconnection(self):
        """Track user disconnection for analytics."""
        # Update the latest EventView with duration
        if self.user.is_authenticated:
            try:
                from django.utils import timezone

                latest_view = (
                    EventView.objects.filter(event_id=self.event_id, user=self.user)
                    .order_by("-created_at")
                    .first()
                )

                if latest_view:
                    duration = (timezone.now() - latest_view.created_at).total_seconds()
                    latest_view.duration = int(duration)
                    latest_view.save()
            except Exception as e:
                logger.error(f"Error tracking disconnection: {e}")

    async def handle_join_session(self, data):
        """Handle user joining a session."""
        session_id = data.get("session_id")
        if not session_id:
            await self.send_error("Missing session_id")
            return

        success = await self.join_session(session_id)
        if success:
            # Notify other participants
            await self.channel_layer.group_send(
                self.event_group_name,
                {
                    "type": "attendance_update",
                    "data": {
                        "session_id": session_id,
                        "user_id": str(self.user.id),
                        "action": "joined",
                    },
                },
            )

    async def handle_leave_session(self, data):
        """Handle user leaving a session."""
        session_id = data.get("session_id")
        if not session_id:
            await self.send_error("Missing session_id")
            return

        success = await self.leave_session(session_id)
        if success:
            # Notify other participants
            await self.channel_layer.group_send(
                self.event_group_name,
                {
                    "type": "attendance_update",
                    "data": {
                        "session_id": session_id,
                        "user_id": str(self.user.id),
                        "action": "left",
                    },
                },
            )

    @database_sync_to_async
    def join_session(self, session_id):
        """Mark user as attending a session."""
        try:
            if not self.user.is_authenticated:
                return False

            session = Session.objects.get(id=session_id, event_id=self.event_id)
            participant = Participant.objects.get(
                user=self.user,
                event_id=self.event_id,
                registration_status=Participant.RegistrationStatus.CONFIRMED,
            )

            participant.sessions_attended.add(session)
            participant.add_points(5, f"Attended session: {session.title}")

            return True

        except (Session.DoesNotExist, Participant.DoesNotExist):
            return False

    @database_sync_to_async
    def leave_session(self, session_id):
        """Mark user as leaving a session."""
        try:
            if not self.user.is_authenticated:
                return False

            Session.objects.get(id=session_id, event_id=self.event_id)
            Participant.objects.get(user=self.user, event_id=self.event_id)

            # Don't remove from attended sessions, just track the leave
            # Could be used for analytics

            return True

        except (Session.DoesNotExist, Participant.DoesNotExist):
            return False

    async def handle_location_update(self, data):
        """Handle user location update within venue."""
        location = data.get("location")
        if not location:
            return

        # Store location for proximity-based networking
        await self.update_user_location(location)

    @database_sync_to_async
    def update_user_location(self, location):
        """Update user's current location in venue."""
        # This could be stored in a cache or database for real-time proximity matching
        pass

    async def handle_poll_response(self, data):
        """Handle poll response from user."""
        poll_id = data.get("poll_id")
        response = data.get("response")

        if not poll_id or response is None:
            await self.send_error("Missing poll_id or response")
            return

        # Process poll response and broadcast results
        await self.channel_layer.group_send(
            self.event_group_name,
            {
                "type": "poll_update",
                "data": {
                    "poll_id": poll_id,
                    "response": response,
                    "user_id": str(self.user.id),
                },
            },
        )

    async def handle_qa_question(self, data):
        """Handle Q&A question from user."""
        question = data.get("question")
        session_id = data.get("session_id")

        if not question or not session_id:
            await self.send_error("Missing question or session_id")
            return

        # Broadcast Q&A question to moderators and speakers
        await self.channel_layer.group_send(
            self.event_group_name,
            {
                "type": "qa_update",
                "data": {
                    "question": question,
                    "session_id": session_id,
                    "user_id": str(self.user.id),
                    "user_name": self.user.get_full_name() or self.user.username,
                    "timestamp": json.dumps(timezone.now(), default=str),
                },
            },
        )

    async def handle_networking_request(self, data):
        """Handle networking connection request."""
        target_user_id = data.get("target_user_id")
        message = data.get("message", "")

        if not target_user_id:
            await self.send_error("Missing target_user_id")
            return

        # Send networking request to target user
        await self.channel_layer.group_send(
            self.event_group_name,
            {
                "type": "networking_update",
                "data": {
                    "type": "connection_request",
                    "from_user_id": str(self.user.id),
                    "from_user_name": self.user.get_full_name() or self.user.username,
                    "to_user_id": target_user_id,
                    "message": message,
                    "timestamp": json.dumps(timezone.now(), default=str),
                },
            },
        )

    async def handle_chat_message(self, data):
        """Handle chat message."""
        message = data.get("message")
        chat_type = data.get("chat_type", "general")  # general, session, networking
        target_id = data.get(
            "target_id"
        )  # session_id for session chat, user_id for direct message

        if not message:
            await self.send_error("Missing message")
            return

        # Broadcast chat message
        await self.channel_layer.group_send(
            self.event_group_name,
            {
                "type": "chat_message",
                "data": {
                    "message": message,
                    "chat_type": chat_type,
                    "target_id": target_id,
                    "user_id": str(self.user.id),
                    "user_name": self.user.get_full_name() or self.user.username,
                    "timestamp": json.dumps(timezone.now(), default=str),
                },
            },
        )


class SessionConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for session-specific real-time features.

    Handles:
    - Live session updates
    - Q&A management
    - Live polls
    - Screen sharing notifications
    - Attendee presence
    """

    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.session_group_name = f"session_{self.session_id}"
        self.user = self.scope["user"]

        # Verify user has access to this session
        if not await self.user_can_access_session():
            await self.close()
            return

        # Join session group
        await self.channel_layer.group_add(self.session_group_name, self.channel_name)

        await self.accept()

        # Send initial session data
        await self.send_session_data()

        logger.info(f"User {self.user} connected to session {self.session_id}")

    async def disconnect(self, close_code):
        # Leave session group
        await self.channel_layer.group_discard(
            self.session_group_name, self.channel_name
        )

        logger.info(f"User {self.user} disconnected from session {self.session_id}")

    @database_sync_to_async
    def user_can_access_session(self):
        """Check if user can access this session."""
        try:
            if not self.user.is_authenticated:
                return False

            session = Session.objects.select_related("event").get(id=self.session_id)
            event = session.event

            # Check if user is registered for the event
            if event.visibility == Event.Visibility.PUBLIC:
                return True

            return Participant.objects.filter(user=self.user, event=event).exists()

        except Session.DoesNotExist:
            return False

    @database_sync_to_async
    def get_session_data(self):
        """Get current session data."""
        try:
            session = Session.objects.select_related("event").get(id=self.session_id)
            return {
                "id": str(session.id),
                "title": session.title,
                "status": session.status,
                "start_time": session.start_time.isoformat(),
                "end_time": session.end_time.isoformat(),
                "is_live": session.is_live,
                "attendee_count": session.attendee_count,
            }
        except Session.DoesNotExist:
            return None

    async def send_session_data(self):
        """Send initial session data to client."""
        session_data = await self.get_session_data()
        if session_data:
            await self.send_json({"type": "session_data", "data": session_data})

    async def send_json(self, data):
        """Send JSON data to WebSocket."""
        await self.send(text_data=json.dumps(data))


class NetworkingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for networking features.

    Handles:
    - Proximity-based networking
    - Interest matching
    - Real-time connection requests
    - Networking events
    """

    async def connect(self):
        self.event_id = self.scope["url_route"]["kwargs"]["event_id"]
        self.networking_group_name = f"networking_{self.event_id}"
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        # Join networking group
        await self.channel_layer.group_add(
            self.networking_group_name, self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave networking group
        await self.channel_layer.group_discard(
            self.networking_group_name, self.channel_name
        )

    async def receive(self, text_data):
        """Handle networking-specific messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "find_matches":
                await self.find_networking_matches()
            elif message_type == "send_connection_request":
                await self.send_connection_request(data)
            elif message_type == "accept_connection":
                await self.accept_connection(data)

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")

    async def find_networking_matches(self):
        """Find potential networking matches for the user."""
        # Implementation for finding matches based on interests, location, etc.
        pass

    async def send_connection_request(self, data):
        """Send a connection request to another user."""
        # Implementation for sending connection requests
        pass

    async def accept_connection(self, data):
        """Accept a connection request."""
        # Implementation for accepting connections
        pass

    async def send_json(self, data):
        """Send JSON data to WebSocket."""
        await self.send(text_data=json.dumps(data))

    async def send_error(self, message):
        """Send error message to client."""
        await self.send_json({"type": "error", "message": message})
