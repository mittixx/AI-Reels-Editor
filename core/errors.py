from __future__ import annotations


class AppError(Exception):
    code = "APP_ERROR"
    exit_code = 1
    requires_user_action = False


class ValidationAppError(AppError):
    code = "VALIDATION_ERROR"
    exit_code = 2


class ProjectNotFoundError(AppError):
    code = "PROJECT_NOT_FOUND"
    exit_code = 3


class DependencyError(AppError):
    code = "DEPENDENCY_MISSING"
    exit_code = 4
    requires_user_action = True


class AIUnavailableError(AppError):
    code = "AI_UNAVAILABLE"
    exit_code = 5
    requires_user_action = True


class RenderError(AppError):
    code = "RENDER_FAILED"
    exit_code = 6


class QCError(AppError):
    code = "QC_FAILED"
    exit_code = 8


class StateError(AppError):
    code = "STATE_ERROR"


class ExternalProcessError(AppError):
    code = "EXTERNAL_PROCESS_ERROR"
