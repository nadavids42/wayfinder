"""Career configuration loading and validation."""

from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(Exception):
    """Raised when career configuration is invalid."""


REQUIRED_SECTIONS = {
    "profile",
    "target_roles",
    "compensation",
    "location",
    "travel",
    "work_preferences",
    "evaluation",
    "constraints",
}

REQUIRED_WEIGHTS = {
    "technical_fit",
    "compensation",
    "location",
    "travel",
    "career_potential",
}


def load_config(path: str | Path) -> dict[str, Any]:
    """
    Load and validate a career configuration YAML file.

    Args:
        path: Path to the YAML configuration.

    Returns:
        Validated configuration dictionary.

    Raises:
        ConfigurationError: If configuration is missing or invalid.
    """

    config_path = Path(path)

    if not config_path.is_file():
        raise ConfigurationError(
            f"Configuration file not found: {config_path}"
        )

    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Invalid YAML configuration: {exc}"
        ) from exc

    except OSError as exc:
        raise ConfigurationError(
            f"Unable to read configuration: {exc}"
        ) from exc

    validate_config(config)

    return config


def validate_config(config: Any) -> None:
    """
    Validate the structure and scoring weights
    of the career configuration.
    """

    if not isinstance(config, dict):
        raise ConfigurationError(
            "Configuration must be a YAML mapping."
        )

    missing_sections = REQUIRED_SECTIONS - config.keys()

    if missing_sections:
        raise ConfigurationError(
            "Missing configuration sections: "
            + ", ".join(sorted(missing_sections))
        )

    evaluation = config["evaluation"]

    if not isinstance(evaluation, dict):
        raise ConfigurationError(
            "'evaluation' must be a mapping."
        )

    weights = evaluation.get("weights")

    if not isinstance(weights, dict):
        raise ConfigurationError(
            "'evaluation.weights' must be a mapping."
        )

    missing_weights = REQUIRED_WEIGHTS - weights.keys()

    if missing_weights:
        raise ConfigurationError(
            "Missing evaluation weights: "
            + ", ".join(sorted(missing_weights))
        )

    unexpected_weights = weights.keys() - REQUIRED_WEIGHTS

    if unexpected_weights:
        raise ConfigurationError(
            "Unexpected evaluation weights: "
            + ", ".join(sorted(unexpected_weights))
        )

    for name, value in weights.items():

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 1
        ):
            raise ConfigurationError(
                f"Invalid weight '{name}': {value}"
            )

    total_weight = sum(weights.values())

    if abs(total_weight - 1.0) > 1e-6:
        raise ConfigurationError(
            "Evaluation weights must sum to 1.0. "
            f"Current total: {total_weight}"
        )

    minimum_score = evaluation.get(
        "minimum_recommendation_score"
    )

    if (
        isinstance(minimum_score, bool)
        or not isinstance(minimum_score, (int, float))
        or not 0 <= minimum_score <= 100
    ):
        raise ConfigurationError(
            "minimum_recommendation_score must be "
            "between 0 and 100."
        )