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


class IsAdmission(BasePermission):
    """Only admission officers and admins can manage student records."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ('admission', 'admin')
        )


class IsDeptAdmin(BasePermission):
    """Only department admins and admins can access dept admin endpoints."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ('dept_admin', 'admin')
        )


class IsDeptAdminOrQA(BasePermission):
    """
    Dept admins, QA officers, and superadmins.

    Used for actions that are primarily a dept_admin responsibility but
    where QA needs university-wide oversight access — e.g. finalizing a
    course. Views using this class must still apply their own dept-scoping
    logic for the dept_admin case (see FinalizeCourseView).
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role in ('dept_admin', 'qa', 'admin')
        )
