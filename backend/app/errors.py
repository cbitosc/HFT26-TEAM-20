"""Domain errors. Each carries the HTTP status and a stable machine-readable code."""


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404

    def __init__(self, resource: str, identifier: str):
        self.code = f"{resource.upper()}_NOT_FOUND"
        super().__init__(f"{resource.capitalize()} '{str(identifier)[:64]}' was not found.")


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class InvalidTransitionError(ConflictError):
    code = "INVALID_TRANSITION"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class EvaluationExecutionDisabledError(ForbiddenError):
    """Candidate code execution is switched off for this deployment."""

    code = "EVALUATION_EXECUTION_DISABLED"


class EvaluationSuiteUnavailableError(ConflictError):
    """The task has no usable trusted evaluation suite (missing, unknown or empty)."""

    code = "EVALUATION_SUITE_UNAVAILABLE"


class EvaluationRequiredError(ConflictError):
    """A decision needs a complete evaluation that does not exist (yet). Nothing is recorded."""

    code = "EVALUATION_REQUIRED"


class EvaluationNotComparableError(ConflictError):
    """Two evaluations used a different suite or evaluator version, so they cannot be compared."""

    code = "EVALUATION_NOT_COMPARABLE"


class ExecutionMismatchError(ConflictError):
    code = "EXECUTION_MISMATCH"


class CodeHashMismatchError(ConflictError):
    """Stored code no longer matches its recorded SHA-256 (or the hash an evaluation recorded)."""

    code = "CODE_HASH_MISMATCH"


class SuiteUploadRejectedError(AppError):
    """A declarative suite upload is malformed or unsafe. The message echoes the client's own input only."""

    status_code = 422
    code = "SUITE_UPLOAD_REJECTED"


class HiddenSuiteUnavailableError(ConflictError):
    """Hidden-suite encryption is not available (no key), so an uploaded suite cannot be sealed."""

    code = "HIDDEN_SUITE_UNAVAILABLE"


class EvidenceNotExportableError(ConflictError):
    """Only validated_improvement and rejected_attempt records can be exported as bundles."""

    code = "EVIDENCE_NOT_EXPORTABLE"


class RunAlreadyStartedError(ConflictError):
    """A run was already claimed for this execution (by this or an earlier server process)."""

    code = "RUN_ALREADY_STARTED"


class LLMBudgetExceededError(AppError):
    """The per-execution cap on LLM calls or tokens was reached. Fails the run with a partial record."""

    status_code = 500

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class LLMNotConfiguredError(AppError):
    """A run needs the Featherless API key, and none is configured."""

    status_code = 503
    code = "LLM_NOT_CONFIGURED"


class BaselineRequiredError(ConflictError):
    """A revision cannot be judged before the baseline (V1) has been accepted."""

    code = "BASELINE_REQUIRED"


class LessonRejectedError(AppError):
    """A would-be transferable lesson contained hidden test data and was refused (not stored)."""

    status_code = 422
    code = "LESSON_REJECTED"
