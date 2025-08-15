"""
Permissions for the events app.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework import permissions

from .models import Event, Participant

User = get_user_model()


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission that allows owners to edit their objects, others to read only.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions for any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions only to the owner
        return getattr(obj, "organizer", None) == request.user


class IsEventOrganizerOrCollaborator(permissions.BasePermission):
    """
    Permission that allows event organizers and collaborators to modify events.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        if not request.user.is_authenticated:
            return False

        # Check if user is organizer
        if getattr(obj, "organizer", None) == request.user:
            return True

        # Check if user is collaborator
        if (
            hasattr(obj, "collaborators")
            and obj.collaborators.filter(id=request.user.id).exists()
        ):
            return True

        # Check if user has explicit permission
        return request.user.has_perm("events.change_event", obj)


class CanModerateEvent(permissions.BasePermission):
    """
    Permission for event moderation activities.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Staff can always moderate
        if request.user.is_staff:
            return True

        # Event organizer can moderate
        if getattr(obj, "organizer", None) == request.user:
            return True

        # Check explicit moderation permission
        return request.user.has_perm("events.moderate_event", obj)


class IsParticipantOrOrganizer(permissions.BasePermission):
    """
    Permission for participant-related actions.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Check if user is the participant
        if hasattr(obj, "user") and obj.user == request.user:
            return True

        # Check if user is event organizer
        if hasattr(obj, "event"):
            event = obj.event
            if event.organizer == request.user:
                return True

            # Check if user is collaborator
            if event.collaborators.filter(id=request.user.id).exists():
                return True

        return False


class CanViewEvent(permissions.BasePermission):
    """
    Permission to view events based on visibility and user permissions.
    """

    def has_object_permission(self, request, view, obj):
        # Public events can be viewed by anyone
        if obj.visibility == Event.Visibility.PUBLIC:
            return True

        # Private events require authentication
        if not request.user.is_authenticated:
            return False

        # Event organizer can always view
        if obj.organizer == request.user:
            return True

        # Collaborators can view
        if obj.collaborators.filter(id=request.user.id).exists():
            return True

        # Participants can view
        if obj.participants.filter(user=request.user).exists():
            return True

        # Check explicit view permission
        return request.user.has_perm("events.view_event", obj)


class IsSessionSpeakerOrOrganizer(permissions.BasePermission):
    """
    Permission for session-related actions.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Event organizer can manage sessions
        if obj.event.organizer == request.user:
            return True

        # Event collaborators can manage sessions
        if obj.event.collaborators.filter(id=request.user.id).exists():
            return True

        # Session speakers can manage their sessions
        if obj.participants.filter(
            user=request.user, role=Participant.Role.SPEAKER
        ).exists():
            return True

        return False


class CanManageExhibitor(permissions.BasePermission):
    """
    Permission for exhibitor management.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Event organizer can manage exhibitors
        if obj.event.organizer == request.user:
            return True

        # Event collaborators can manage exhibitors
        if obj.event.collaborators.filter(id=request.user.id).exists():
            return True

        # Exhibitor contact person can manage
        if getattr(obj, "contact_person", None) == request.user:
            return True

        return False


class CanAccessAnalytics(permissions.BasePermission):
    """
    Permission for accessing event analytics.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Staff can access all analytics
        if request.user.is_staff:
            return True

        # Get the event from the analytics object
        event = getattr(obj, "event", obj)

        # Event organizer can access analytics
        if event.organizer == request.user:
            return True

        # Event collaborators can access analytics
        if event.collaborators.filter(id=request.user.id).exists():
            return True

        return False


class IsRegisteredParticipant(permissions.BasePermission):
    """
    Permission that checks if user is a registered participant of an event.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Get the event (obj might be session, exhibitor, etc.)
        event = getattr(obj, "event", obj)

        return event.participants.filter(
            user=request.user,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        ).exists()


class CanRateSession(permissions.BasePermission):
    """
    Permission for rating sessions.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # User must be a confirmed participant of the event
        return obj.event.participants.filter(
            user=request.user,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        ).exists()


class IsEventOwnerOrStaff(permissions.BasePermission):
    """
    Permission that allows only event owners or staff to perform actions.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Staff can do anything
        if request.user.is_staff:
            return True

        # Get the event from various object types
        if hasattr(obj, "event"):
            event = obj.event
        elif hasattr(obj, "organizer"):
            event = obj
        else:
            return False

        return event.organizer == request.user


class CanManageEventContent(permissions.BasePermission):
    """
    Permission for managing event content (sessions, attachments, etc.).
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        # Get the event
        event = getattr(obj, "event", obj)

        # Event organizer can manage content
        if event.organizer == request.user:
            return True

        # Event collaborators can manage content
        if event.collaborators.filter(id=request.user.id).exists():
            return True

        # Check if user has content management permission
        return request.user.has_perm("events.manage_content", event)


class DynamicEventPermission(permissions.BasePermission):
    """
    Dynamic permission that checks various event-related permissions.
    """

    def has_permission(self, request, view):
        # Allow authenticated users for most operations
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # For safe methods, use visibility-based permissions
        if request.method in permissions.SAFE_METHODS:
            return self._can_view_object(request.user, obj)

        # For unsafe methods, check ownership/collaboration
        return self._can_modify_object(request.user, obj)

    def _can_view_object(self, user, obj):
        """Check if user can view the object."""
        # Get the event
        event = getattr(obj, "event", obj)

        # Public events are viewable by everyone
        if getattr(event, "visibility", None) == Event.Visibility.PUBLIC:
            return True

        # Anonymous users can't view private content
        if isinstance(user, AnonymousUser):
            return False

        # Organizers and collaborators can view
        if event.organizer == user or event.collaborators.filter(id=user.id).exists():
            return True

        # Participants can view
        if event.participants.filter(user=user).exists():
            return True

        # Check explicit permissions
        return user.has_perm("events.view_event", event)

    def _can_modify_object(self, user, obj):
        """Check if user can modify the object."""
        if isinstance(user, AnonymousUser):
            return False

        # Staff can modify anything
        if user.is_staff:
            return True

        # Get the event
        event = getattr(obj, "event", obj)

        # Organizers can modify
        if event.organizer == user:
            return True

        # Collaborators can modify
        if event.collaborators.filter(id=user.id).exists():
            return True

        # Check explicit permissions
        return user.has_perm("events.change_event", event)
