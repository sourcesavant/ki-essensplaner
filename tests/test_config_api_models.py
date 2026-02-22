import pytest
from pydantic import ValidationError

from src.api.routers.config import UpdateConfigRequest


def test_update_config_request_requires_at_least_one_field() -> None:
    with pytest.raises(ValidationError):
        UpdateConfigRequest()


def test_update_config_request_accepts_rotation_only() -> None:
    req = UpdateConfigRequest(
        rotation_policy={
            "no_repeat_weeks": 1,
            "favorite_min_return_weeks": 3,
            "favorite_return_bonus_per_week": 2.0,
            "favorite_return_bonus_max": 10.0,
        }
    )
    assert req.household_size is None
    assert req.rotation_policy is not None
