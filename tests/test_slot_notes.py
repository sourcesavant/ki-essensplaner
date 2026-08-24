from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.agents.models import (
    SlotRecommendation,
    WeeklyRecommendation,
    load_weekly_plan,
    save_weekly_plan,
)
from src.api.routers import weekly_plan as weekly_plan_router
from src.api.schemas.weekly_plan import UpdateSlotNoteRequest


def _plan(note: str | None = None) -> WeeklyRecommendation:
    return WeeklyRecommendation(
        week_start="2026-08-29",
        slots=[SlotRecommendation(weekday="Montag", slot="Abendessen", note=note)],
    )


def test_slot_note_round_trip_and_legacy_compatibility(tmp_path: Path) -> None:
    path = tmp_path / "weekly_plan.json"
    save_weekly_plan(_plan("Kartoffeln sind vorhanden"), path)

    loaded = load_weekly_plan(path)
    assert loaded is not None
    assert loaded.get_slot("Montag", "Abendessen").note == "Kartoffeln sind vorhanden"

    legacy = WeeklyRecommendation.from_dict(
        {"slots": [{"weekday": "Montag", "slot": "Abendessen", "recommendations": []}]}
    )
    assert legacy.get_slot("Montag", "Abendessen").note is None


def test_new_plan_does_not_inherit_slot_note() -> None:
    current = _plan("Nicht übernehmen")
    regenerated = _plan()

    assert current.get_slot("Montag", "Abendessen").note == "Nicht übernehmen"
    assert regenerated.get_slot("Montag", "Abendessen").note is None


def test_update_slot_note_saves_trimmed_value_and_empty_clears(monkeypatch) -> None:
    plan = _plan()
    saved: list[WeeklyRecommendation] = []
    monkeypatch.setattr(weekly_plan_router, "load_weekly_plan", lambda: plan)
    monkeypatch.setattr(weekly_plan_router, "save_weekly_plan", saved.append)

    response = weekly_plan_router.update_slot_note(
        UpdateSlotNoteRequest(weekday="Montag", slot="Abendessen", note="  Rest essen  "),
        _token="test",
    )
    assert plan.get_slot("Montag", "Abendessen").note == "Rest essen"
    assert response.slots[0].note == "Rest essen"
    assert saved == [plan]

    weekly_plan_router.update_slot_note(
        UpdateSlotNoteRequest(weekday="Montag", slot="Abendessen", note="   "),
        _token="test",
    )
    assert plan.get_slot("Montag", "Abendessen").note is None


def test_update_slot_note_validates_length_and_slot(monkeypatch) -> None:
    with pytest.raises(ValidationError):
        UpdateSlotNoteRequest(weekday="Montag", slot="Abendessen", note="x" * 501)

    monkeypatch.setattr(weekly_plan_router, "load_weekly_plan", _plan)
    with pytest.raises(HTTPException) as exc_info:
        weekly_plan_router.update_slot_note(
            UpdateSlotNoteRequest(weekday="Montag", slot="Frühstück", note="Test"),
            _token="test",
        )
    assert exc_info.value.status_code == 400
