from src.verification.cross_validator import CrossValidator, cross_validator

def get_cross_validator() -> CrossValidator:
    """Provides CrossValidator singleton for dependency injection in endpoints."""
    return cross_validator
