"""Tests for career configuration loading."""

from copy import deepcopy
from pathlib import Path

import pytest

from wayfinder.config import (
    ConfigurationError,
    load_config,
    validate_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "career.yaml"


@pytest.fixture
def valid_config():
    """Return a fresh copy of the real configuration."""

    return deepcopy(load_config(CONFIG_PATH))


def test_load_valid_configuration():
    """The career configuration should load successfully."""

    config = load_config(CONFIG_PATH)

    assert config["profile"]["current_company"] == "Bullhorn"

    assert config["compensation"]["target_base_salary"] == 170000

    assert config["location"]["preferred"] == "remote"


def test_missing_configuration_file():
    """Missing files should raise ConfigurationError."""

    with pytest.raises(
        ConfigurationError,
        match="Configuration file not found",
    ):
        load_config("nonexistent_config.yaml")


def test_missing_required_section(valid_config):
    """Missing required sections should be rejected."""

    del valid_config["compensation"]

    with pytest.raises(
        ConfigurationError,
        match="Missing configuration sections",
    ):
        validate_config(valid_config)


def test_invalid_weight_total(valid_config):
    """Evaluation weights must sum to 1.0."""

    valid_config["evaluation"]["weights"]["technical_fit"] = 0.50

    with pytest.raises(
        ConfigurationError,
        match="must sum to 1.0",
    ):
        validate_config(valid_config)


def test_negative_weight(valid_config):
    """Negative scoring weights should be rejected."""

    valid_config["evaluation"]["weights"]["travel"] = -0.10

    with pytest.raises(
        ConfigurationError,
        match="Invalid weight",
    ):
        validate_config(valid_config)


def test_invalid_minimum_score(valid_config):
    """Recommendation thresholds must be between 0 and 100."""

    valid_config["evaluation"][
        "minimum_recommendation_score"
    ] = 150

    with pytest.raises(
        ConfigurationError,
        match="between 0 and 100",
    ):
        validate_config(valid_config)


def test_missing_evaluation_weight(valid_config):
    """All scoring dimensions must be present."""

    del valid_config["evaluation"]["weights"]["travel"]

    with pytest.raises(
        ConfigurationError,
        match="Missing evaluation weights",
    ):
        validate_config(valid_config)


def test_boolean_weight_rejected(valid_config):
    """Booleans must not be accepted as numeric weights."""

    valid_config["evaluation"]["weights"]["travel"] = True

    with pytest.raises(
        ConfigurationError,
        match="Invalid weight",
    ):
        validate_config(valid_config)