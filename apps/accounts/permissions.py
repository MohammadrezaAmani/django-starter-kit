from django.contrib.auth import get_user_model
from rest_framework import permissions

from .models import (
    Connection,
    Department,
    NetworkMembership,
    UserDepartment,
    UserRole,
)

User = get_user_model()


class IsAdminUserOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admin users to create, update, and delete objects.
    Read-only access is allowed for other users.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access the view.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_staff


class IsVerifiedUser(permissions.BasePermission):
    """
    Custom permission to only allow verified users to access the view.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_verified


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to edit it.
    """

    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_staff:
            return True

        if hasattr(obj, "user"):
            return obj.user == request.user

        if hasattr(obj, "owner"):
            return obj.owner == request.user

        if hasattr(obj, "id") and hasattr(request.user, "id"):
            return obj.id == request.user.id

        return False


class IsChatOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission for chat objects that checks creator field.
    """

    def has_object_permission(self, request, view, obj):
        # Admin users can always edit
        if request.user and request.user.is_staff:
            return True

        # Check if user is the chat creator
        if hasattr(obj, "creator"):
            return obj.creator == request.user

        # Check if user is an admin participant in the chat
        if hasattr(obj, "chatparticipant_set"):
            try:
                from apps.chats.models import ChatParticipant

                participant = obj.chatparticipant_set.get(user=request.user)
                return participant.role in [
                    ChatParticipant.ParticipantRole.OWNER,
                    ChatParticipant.ParticipantRole.ADMIN,
                ]
            except:
                pass

        return False


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners to edit, but allow read access to others.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        if hasattr(obj, "user"):
            return obj.user == request.user

        if hasattr(obj, "owner"):
            return obj.owner == request.user

        return False


class HasRole(permissions.BasePermission):
    """
    Permission class to check if user has specific role.
    Usage: permission_classes = [HasRole('admin'), HasRole('manager')]
    """

    def __init__(self, role_name):
        self.role_name = role_name

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if user has the required role
        return UserRole.objects.filter(
            user=request.user,
            role__name=self.role_name,
            is_active=True,
        ).exists()

    def __call__(self):
        return self


class HasAnyRole(permissions.BasePermission):
    """
    Permission class to check if user has any of the specified roles.
    Usage: permission_classes = [HasAnyRole(['admin', 'manager', 'hr'])]
    """

    def __init__(self, role_names):
        self.role_names = role_names if isinstance(role_names, list) else [role_names]

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return UserRole.objects.filter(
            user=request.user,
            role__name__in=self.role_names,
            is_active=True,
        ).exists()

    def __call__(self):
        return self


class CanViewProfile(permissions.BasePermission):
    """
    Permission to view user profiles based on visibility settings.
    """

    def has_object_permission(self, request, view, obj):
        # Get the user whose profile is being viewed
        profile_user = obj if isinstance(obj, User) else obj.user

        # Owner can always view their own profile
        if request.user == profile_user:
            return True

        # Admin can view any profile
        if request.user.is_staff:
            return True

        # Check profile visibility settings
        profile = getattr(profile_user, "profile", None)
        if not profile:
            return False

        if profile.profile_visibility == "public":
            return True
        elif profile.profile_visibility == "private":
            return False
        elif profile.profile_visibility == "connections-only":
            # Check if users are connected
            return Connection.objects.filter(
                models.Q(from_user=request.user, to_user=profile_user)
                | models.Q(from_user=profile_user, to_user=request.user),
                status=Connection.ConnectionStatus.ACCEPTED,
            ).exists()

        return False


class CanSendConnectionRequest(permissions.BasePermission):
    """
    Permission to send connection requests.
    """

    def has_object_permission(self, request, view, obj):
        target_user = obj if isinstance(obj, User) else obj.user

        # Cannot send request to self
        if request.user == target_user:
            return False

        # Check if user allows connections
        profile = getattr(target_user, "profile", None)
        if profile and not profile.allow_connections:
            return False

        # Check if connection already exists
        existing_connection = Connection.objects.filter(
            models.Q(from_user=request.user, to_user=target_user)
            | models.Q(from_user=target_user, to_user=request.user)
        ).exists()

        return not existing_connection


class CanSendMessage(permissions.BasePermission):
    """
    Permission to send messages to users.
    """

    def has_object_permission(self, request, view, obj):
        target_user = obj if isinstance(obj, User) else obj.user

        # Cannot message self
        if request.user == target_user:
            return False

        # Check if user allows messages
        profile = getattr(target_user, "profile", None)
        if profile and not profile.allow_messages:
            # Only allow if users are connected
            return Connection.objects.filter(
                models.Q(from_user=request.user, to_user=target_user)
                | models.Q(from_user=target_user, to_user=request.user),
                status=Connection.ConnectionStatus.ACCEPTED,
            ).exists()

        return True


class CanEndorseSkill(permissions.BasePermission):
    """
    Permission to endorse user skills.
    """

    def has_object_permission(self, request, view, obj):
        skill_owner = obj.user if hasattr(obj, "user") else obj

        # Cannot endorse own skills
        if request.user == skill_owner:
            return False

        # Check if skill owner allows endorsements
        profile = getattr(skill_owner, "profile", None)
        if profile and not profile.allow_endorsements:
            return False

        # Must be connected or profile is public
        if profile and profile.profile_visibility == "private":
            return Connection.objects.filter(
                models.Q(from_user=request.user, to_user=skill_owner)
                | models.Q(from_user=skill_owner, to_user=request.user),
                status=Connection.ConnectionStatus.ACCEPTED,
            ).exists()

        return True


class IsDepartmentHead(permissions.BasePermission):
    """
    Permission for department heads to manage their department.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return Department.objects.filter(head=request.user).exists()

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if user is head of the department
        if hasattr(obj, "department"):
            return obj.department.head == request.user
        elif isinstance(obj, Department):
            return obj.head == request.user

        return False


class IsDepartmentMember(permissions.BasePermission):
    """
    Permission for department members.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return UserDepartment.objects.filter(user=request.user).exists()

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if user is member of the same department
        if hasattr(obj, "user"):
            user_departments = set(
                UserDepartment.objects.filter(user=request.user).values_list(
                    "department", flat=True
                )
            )
            obj_departments = set(
                UserDepartment.objects.filter(user=obj.user).values_list(
                    "department", flat=True
                )
            )
            return bool(user_departments.intersection(obj_departments))

        return False


class IsTaskAssigneeOrCreator(permissions.BasePermission):
    """
    Permission for task assignees and creators.
    """

    def has_object_permission(self, request, view, obj):
        return obj.assignee == request.user or obj.created_by == request.user


class IsNetworkAdmin(permissions.BasePermission):
    """
    Permission for network administrators.
    """

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, "network"):
            network = obj.network
        elif hasattr(obj, "admins"):
            network = obj
        else:
            return False

        return (
            network.created_by == request.user or request.user in network.admins.all()
        )


class IsNetworkMember(permissions.BasePermission):
    """
    Permission for network members.
    """

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, "network"):
            network = obj.network
        elif hasattr(obj, "memberships"):
            network = obj
        else:
            return False

        return NetworkMembership.objects.filter(
            user=request.user,
            network=network,
            status=NetworkMembership.MembershipStatus.ACTIVE,
        ).exists()


class CanAccessRecommendation(permissions.BasePermission):
    """
    Permission to access recommendations.
    """

    def has_object_permission(self, request, view, obj):
        # Recommender and recommendee can always access
        if request.user in [obj.recommender, obj.recommendee]:
            return True

        # Public recommendations can be viewed by anyone
        if obj.is_public:
            return True

        # Private recommendations only visible to involved parties
        return False


class RateLimitedPermission(permissions.BasePermission):
    """
    Base permission class that includes rate limiting.
    """

    def has_permission(self, request, view):
        # This can be extended with specific rate limiting logic
        return True


# Role-based permission decorators
def requires_role(role_name):
    """
    Decorator to require a specific role for a view method.
    """

    def decorator(view_func):
        def wrapper(self, request, *args, **kwargs):
            if not request.user.is_authenticated:
                return permissions.PermissionDenied("Authentication required")

            if not UserRole.objects.filter(
                user=request.user, role__name=role_name, is_active=True
            ).exists():
                return permissions.PermissionDenied(
                    f"Role '{role_name}' required for this action"
                )

            return view_func(self, request, *args, **kwargs)

        return wrapper

    return decorator


def requires_any_role(role_names):
    """
    Decorator to require any of the specified roles for a view method.
    """

    def decorator(view_func):
        def wrapper(self, request, *args, **kwargs):
            if not request.user.is_authenticated:
                return permissions.PermissionDenied("Authentication required")

            if not UserRole.objects.filter(
                user=request.user, role__name__in=role_names, is_active=True
            ).exists():
                return permissions.PermissionDenied(
                    f"One of roles {role_names} required for this action"
                )

            return view_func(self, request, *args, **kwargs)

        return wrapper

    return decorator


# Permission helper functions
def can_view_user_profile(viewer, profile_user):
    """
    Helper function to check if a user can view another user's profile.
    """
    if viewer == profile_user:
        return True

    if viewer.is_staff:
        return True

    profile = getattr(profile_user, "profile", None)
    if not profile:
        return False

    if profile.profile_visibility == "public":
        return True
    elif profile.profile_visibility == "private":
        return False
    elif profile.profile_visibility == "connections-only":
        return Connection.objects.filter(
            models.Q(from_user=viewer, to_user=profile_user)
            | models.Q(from_user=profile_user, to_user=viewer),
            status=Connection.ConnectionStatus.ACCEPTED,
        ).exists()

    return False


def can_send_connection_request(sender, recipient):
    """
    Helper function to check if a user can send a connection request.
    """
    if sender == recipient:
        return False

    profile = getattr(recipient, "profile", None)
    if profile and not profile.allow_connections:
        return False

    existing_connection = Connection.objects.filter(
        models.Q(from_user=sender, to_user=recipient)
        | models.Q(from_user=recipient, to_user=sender)
    ).exists()

    return not existing_connection


def can_send_message(sender, recipient):
    """
    Helper function to check if a user can send a message.
    """
    if sender == recipient:
        return False

    profile = getattr(recipient, "profile", None)
    if profile and not profile.allow_messages:
        # Only allow if users are connected
        return Connection.objects.filter(
            models.Q(from_user=sender, to_user=recipient)
            | models.Q(from_user=recipient, to_user=sender),
            status=Connection.ConnectionStatus.ACCEPTED,
        ).exists()

    return True


def can_endorse_skill(endorser, skill_owner):
    """
    Helper function to check if a user can endorse another user's skill.
    """
    if endorser == skill_owner:
        return False

    profile = getattr(skill_owner, "profile", None)
    if profile and not profile.allow_endorsements:
        return False

    # Must be connected or profile is public
    if profile and profile.profile_visibility == "private":
        return Connection.objects.filter(
            models.Q(from_user=endorser, to_user=skill_owner)
            | models.Q(from_user=skill_owner, to_user=endorser),
            status=Connection.ConnectionStatus.ACCEPTED,
        ).exists()

    return True


def has_role(user, role_name):
    """
    Helper function to check if a user has a specific role.
    """
    if not user or not user.is_authenticated:
        return False

    return UserRole.objects.filter(
        user=user, role__name=role_name, is_active=True
    ).exists()


def has_any_role(user, role_names):
    """
    Helper function to check if a user has any of the specified roles.
    """
    if not user or not user.is_authenticated:
        return False

    return UserRole.objects.filter(
        user=user, role__name__in=role_names, is_active=True
    ).exists()


def is_department_head(user, department=None):
    """
    Helper function to check if a user is a department head.
    """
    if not user or not user.is_authenticated:
        return False

    query = Department.objects.filter(head=user)
    if department:
        query = query.filter(id=department.id)

    return query.exists()


def is_department_member(user, department):
    """
    Helper function to check if a user is a member of a department.
    """
    if not user or not user.is_authenticated:
        return False

    return UserDepartment.objects.filter(user=user, department=department).exists()


def is_same_department(user1, user2):
    """
    Helper function to check if two users are in the same department.
    """
    if not user1 or not user2:
        return False

    user1_departments = set(
        UserDepartment.objects.filter(user=user1).values_list("department", flat=True)
    )
    user2_departments = set(
        UserDepartment.objects.filter(user=user2).values_list("department", flat=True)
    )

    return bool(user1_departments.intersection(user2_departments))


def is_network_admin(user, network):
    """
    Helper function to check if a user is a network admin.
    """
    if not user or not user.is_authenticated:
        return False

    return network.created_by == user or user in network.admins.all()


def is_network_member(user, network):
    """
    Helper function to check if a user is a member of a network.
    """
    if not user or not user.is_authenticated:
        return False

    return NetworkMembership.objects.filter(
        user=user,
        network=network,
        status=NetworkMembership.MembershipStatus.ACTIVE,
    ).exists()


def are_connected(user1, user2):
    """
    Helper function to check if two users are connected.
    """
    return Connection.objects.filter(
        models.Q(from_user=user1, to_user=user2)
        | models.Q(from_user=user2, to_user=user1),
        status=Connection.ConnectionStatus.ACCEPTED,
    ).exists()


def can_access_user_data(accessor, target_user, data_type="basic"):
    """
    Comprehensive helper to check data access permissions.

    Args:
        accessor: User trying to access data
        target_user: User whose data is being accessed
        data_type: Type of data ('basic', 'contact', 'experience', etc.)
    """
    if accessor == target_user:
        return True

    if accessor.is_staff:
        return True

    profile = getattr(target_user, "profile", None)
    if not profile:
        return False

    # Check general profile visibility first
    if profile.profile_visibility == "private":
        return False
    elif profile.profile_visibility == "connections-only":
        if not are_connected(accessor, target_user):
            return False

    # Check specific data type permissions
    data_permissions = {
        "contact": profile.show_contact_info,
        "experience": profile.show_experience,
        "education": profile.show_education,
        "skills": profile.show_skills,
        "projects": profile.show_projects,
        "achievements": profile.show_achievements,
        "publications": profile.show_publications,
        "volunteer": profile.show_volunteer,
    }

    return data_permissions.get(data_type, True)


class DataAccessPermission(permissions.BasePermission):
    """
    Permission class for specific data type access.
    """

    def __init__(self, data_type="basic"):
        self.data_type = data_type

    def has_object_permission(self, request, view, obj):
        target_user = obj if isinstance(obj, User) else obj.user
        return can_access_user_data(request.user, target_user, self.data_type)

    def __call__(self):
        return self


# Specific data access permissions
class CanViewContactInfo(DataAccessPermission):
    def __init__(self):
        super().__init__("contact")


class CanViewExperience(DataAccessPermission):
    def __init__(self):
        super().__init__("experience")


class CanViewEducation(DataAccessPermission):
    def __init__(self):
        super().__init__("education")


class CanViewSkills(DataAccessPermission):
    def __init__(self):
        super().__init__("skills")


class CanViewProjects(DataAccessPermission):
    def __init__(self):
        super().__init__("projects")


class CanViewAchievements(DataAccessPermission):
    def __init__(self):
        super().__init__("achievements")


class CanViewPublications(DataAccessPermission):
    def __init__(self):
        super().__init__("publications")


class CanViewVolunteer(DataAccessPermission):
    def __init__(self):
        super().__init__("volunteer")


# Import models for Q objects
from django.db import models
