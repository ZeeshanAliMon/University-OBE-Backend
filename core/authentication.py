from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import PermissionDenied


# Endpoints a user with must_change_password=True is still allowed to hit.
# Keep this list tiny and explicit — anything not listed here is blocked.
ALLOWED_WHILE_PASSWORD_CHANGE_REQUIRED = {
    '/api/auth/change-password/',
}


class PasswordChangeEnforcingJWTAuthentication(JWTAuthentication):
    """
    Drop-in replacement for JWTAuthentication.

    Same token validation as the stock class, but if the authenticated
    user still has must_change_password=True, every request is rejected
    with 403 except the change-password endpoint itself.

    This runs at the authentication layer (before any view's
    permission_classes are evaluated), so a view can't accidentally
    bypass this by setting its own permission_classes — the only way
    around it is to not use this authentication class at all, which
    would be an explicit, visible choice in DEFAULT_AUTHENTICATION_CLASSES
    or a view-level override.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result

        if getattr(user, 'must_change_password', False):
            path = request.path
            # Normalize trailing slash mismatches defensively.
            if path.rstrip('/') + '/' not in ALLOWED_WHILE_PASSWORD_CHANGE_REQUIRED and \
               path not in ALLOWED_WHILE_PASSWORD_CHANGE_REQUIRED:
                raise PermissionDenied(
                    detail='Password change required before continuing.',
                    code='must_change_password'
                )

        return user, validated_token
