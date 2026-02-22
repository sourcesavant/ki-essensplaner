from src.core import user_config


def test_set_rotation_policy_persists_normalized_values(monkeypatch) -> None:
    config_path = user_config.LOCAL_DIR / "test_rotation_config.json"
    if config_path.exists():
        config_path.unlink()
    monkeypatch.setattr(user_config, "CONFIG_PATH", config_path)

    try:
        saved = user_config.set_rotation_policy(
            {
                "no_repeat_weeks": -2,
                "favorite_min_return_weeks": "4",
                "favorite_return_bonus_per_week": "1.5",
                "favorite_return_bonus_max": "invalid",
            }
        )

        assert saved == {
            "no_repeat_weeks": 0,
            "favorite_min_return_weeks": 4,
            "favorite_return_bonus_per_week": 1.5,
            "favorite_return_bonus_max": 10.0,
        }

        loaded = user_config.get_rotation_policy()
        assert loaded == saved
        assert config_path.exists()
    finally:
        if config_path.exists():
            config_path.unlink()
