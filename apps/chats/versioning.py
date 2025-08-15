from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import NotAcceptable
from rest_framework.versioning import BaseVersioning


class CustomHeaderVersioning(BaseVersioning):
    """
    Custom versioning class that uses HTTP_API_VERSION header.
    """

    invalid_version_message = _('Invalid version in "API-Version" header.')

    def determine_version(self, request, *args, **kwargs):
        """
        Determine the API version from the HTTP_API_VERSION header.
        """
        version = request.META.get("HTTP_API_VERSION")

        if version is None:
            # Return default version if no header provided
            return self.default_version

        if not self.is_allowed_version(version):
            raise NotAcceptable(self.invalid_version_message)

        return version

    def reverse(
        self, viewname, args=None, kwargs=None, request=None, format=None, **extra
    ):
        """
        Return a versioned URL.
        """
        url = super().reverse(viewname, args, kwargs, request, format, **extra)
        return url

    def is_allowed_version(self, version):
        """
        Check if the provided version is in the allowed versions list.
        """
        if not hasattr(self, "allowed_versions") or not self.allowed_versions:
            return True
        return version in self.allowed_versions
