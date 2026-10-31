"""
Paquete de validadores modulares para configuración local de MeshCore.
"""

from __future__ import annotations

from src.admin.validators.airtime_policy_validator import (
    validate_airtime_policy_params,
    validate_telemetry_modes,
)
from src.admin.validators.identity_validator import (
    validate_custom_var,
    validate_identity_params,
)
from src.admin.validators.location_validator import (
    validate_location_params,
)
from src.admin.validators.radio_params_validator import (
    validate_radio_params,
    validate_tuning_params,
)
from src.admin.validators.schema import (
    ALLOWED_LOCAL_KEYS,
    OTHER_PARAM_FIELDS,
    UNSUPPORTED_LOCAL_FIELDS,
    LocalConfigValidationError,
    normalize_coding_rate,
    validate_general_schema,
)

__all__ = [
    "ALLOWED_LOCAL_KEYS",
    "OTHER_PARAM_FIELDS",
    "UNSUPPORTED_LOCAL_FIELDS",
    "LocalConfigValidationError",
    "normalize_coding_rate",
    "validate_airtime_policy_params",
    "validate_custom_var",
    "validate_general_schema",
    "validate_identity_params",
    "validate_location_params",
    "validate_radio_params",
    "validate_telemetry_modes",
    "validate_tuning_params",
]
