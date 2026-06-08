class MileageTrackerError(Exception):
    """Base error for domain validation failures."""


class ValidationError(MileageTrackerError):
    """User-facing validation failure with a specific message."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class OdometerOrderingError(ValidationError):
    """Raised when end-of-year odometer is less than start-of-year."""


class VehicleHasTripsError(ValidationError):
    """Raised when attempting to hard-delete a vehicle that has trips."""
