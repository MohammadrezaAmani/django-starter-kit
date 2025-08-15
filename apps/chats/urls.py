from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from . import views

# Main router for top-level resources
router = DefaultRouter()
router.register(r"chats", views.ChatViewSet, basename="chat")
router.register(r"folders", views.ChatFolderViewSet, basename="chatfolder")
router.register(r"bots", views.ChatBotViewSet, basename="chatbot")
router.register(r"sticker-sets", views.ChatStickerSetViewSet, basename="chatstickerset")
router.register(r"themes", views.ChatThemeViewSet, basename="chattheme")

# Nested routers for chat-related resources
chats_router = routers.NestedDefaultRouter(router, r"chats", lookup="chat")
chats_router.register(r"messages", views.ChatMessageViewSet, basename="message")
chats_router.register(
    r"participants", views.ChatParticipantViewSet, basename="chat-participants"
)
chats_router.register(r"polls", views.ChatPollViewSet, basename="chat-polls")
chats_router.register(r"calls", views.ChatCallViewSet, basename="chat-calls")
chats_router.register(
    r"invite-links", views.ChatInviteLinkViewSet, basename="chat-invite-links"
)

urlpatterns = [
    # API routes (versioned)
    path("api/v1/", include(router.urls)),
    path("api/v1/", include(chats_router.urls)),
    # API routes (non-versioned for backward compatibility and tests)
    path("api/", include(router.urls)),
    path("api/", include(chats_router.urls)),
    # Search endpoints
    path(
        "api/chat-search/",
        views.ChatSearchView.as_view({"get": "chats"}),
        name="chat-search",
    ),
    path(
        "api/v1/chat-search/",
        views.ChatSearchView.as_view({"get": "chats"}),
        name="chat-search",
    ),
    # Call actions
    path(
        "api/chats/<uuid:chat_pk>/calls/<uuid:call_pk>/join/",
        views.ChatCallViewSet.as_view({"post": "join"}),
        name="call-join",
    ),
    path(
        "api/chats/<uuid:chat_pk>/calls/<uuid:call_pk>/leave/",
        views.ChatCallViewSet.as_view({"post": "leave"}),
        name="call-leave",
    ),
    path(
        "api/chats/<uuid:chat_pk>/calls/<uuid:call_pk>/end/",
        views.ChatCallViewSet.as_view({"post": "end"}),
        name="call-end",
    ),
    # Export endpoints
    path(
        "api/chats/<uuid:chat_pk>/export/",
        views.ChatExportView.as_view(),
        name="chat-export",
    ),
    # Search endpoints
    path(
        "api/chats/<uuid:chat_pk>/messages/search/",
        views.MessageSearchView.as_view(),
        name="message-search",
    ),
    # File upload
    path(
        "api/chats/<uuid:chat_pk>/upload-file/",
        views.FileUploadView.as_view(),
        name="chat-upload-file",
    ),
    path(
        "api/chats/<uuid:chat_pk>/upload-files/",
        views.MultipleFileUploadView.as_view(),
        name="chat-upload-files",
    ),
    path("api/files/upload/", views.FileUploadView.as_view(), name="file-upload"),
    # Message reactions
    path(
        "api/chats/<uuid:chat_pk>/messages/<uuid:message_pk>/reactions/",
        views.MessageReactionView.as_view(),
        name="message-reaction",
    ),
    # Invite links
    path(
        "api/invite-links/<str:link>/join/",
        views.JoinViaChatInviteLinkView.as_view(),
        name="chat-join-via-link",
    ),
    # Webhooks
    path(
        "api/chats/<uuid:chat_pk>/webhooks/",
        views.WebhookView.as_view(),
        name="chat-webhooks",
    ),
    # User management
    path("api/users/register/", views.UserRegisterView.as_view(), name="user-register"),
    path("api/users/<int:pk>/", views.UserProfileView.as_view(), name="user-profile"),
    # Privacy endpoints
    path(
        "api/user-data-export/",
        views.UserDataExportView.as_view(),
        name="user-data-export",
    ),
    path(
        "api/user-data-delete/",
        views.UserDataDeleteView.as_view(),
        name="user-data-delete",
    ),
]
