from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsQA(BasePermission):
    """Only QA officers and admins can write QA data."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ('qa', 'admin')
        )


class IsQAOrReadOnly(BasePermission):
    """Anyone authenticated can read; only QA/admin can write."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in ('qa', 'admin')


class IsInstructor(BasePermission):
    """Only instructors can access instructor endpoints."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ('instructor', 'admin')
        )
