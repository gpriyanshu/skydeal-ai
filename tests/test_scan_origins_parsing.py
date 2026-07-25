import pytest
from pydantic_settings.exceptions import SettingsError

from src.config import Settings


def test_comma_separated_values():
    settings = Settings(SCAN_ORIGINS="DEL,BOM,BLR")
    assert settings.SCAN_ORIGINS == ["DEL", "BOM", "BLR"]
    assert settings.SCAN_ORIGIN == "DEL"


def test_whitespace():
    settings = Settings(SCAN_ORIGINS="  DEL  ,   BOM   , BLR  ")
    assert settings.SCAN_ORIGINS == ["DEL", "BOM", "BLR"]


def test_lowercase_values():
    settings = Settings(SCAN_ORIGINS="del,bom,blr")
    assert settings.SCAN_ORIGINS == ["DEL", "BOM", "BLR"]


def test_duplicate_origins():
    settings = Settings(SCAN_ORIGINS="DEL,BOM,DEL,BLR,BOM")
    assert settings.SCAN_ORIGINS == ["DEL", "BOM", "BLR"]


def test_empty_entries():
    settings = Settings(SCAN_ORIGINS="DEL,,BOM,,BLR,")
    assert settings.SCAN_ORIGINS == ["DEL", "BOM", "BLR"]


def test_fallback_behaviour():
    # If SCAN_ORIGINS is omitted, fallback to SCAN_ORIGIN
    settings = Settings(SCAN_ORIGIN="BOM", SCAN_ORIGINS=None)
    assert settings.SCAN_ORIGINS == ["BOM"]

    # If both are missing/None, fallback to ["DEL"]
    # We pass None to ensure we test the validation override path
    settings = Settings(SCAN_ORIGIN=None, SCAN_ORIGINS=None)
    assert settings.SCAN_ORIGINS == ["DEL"]


def test_malformed_values():
    # Malformed IATA code (too long)
    with pytest.raises(SettingsError) as exc_info:
        Settings(SCAN_ORIGINS="DEL,BOM1")
    assert "Scan origins must be 3-letter alphabetical IATA airport codes" in str(exc_info.value)

    # Malformed IATA code (contains numbers)
    with pytest.raises(SettingsError) as exc_info:
        Settings(SCAN_ORIGINS="DE1")
    assert "Scan origins must be 3-letter alphabetical IATA airport codes" in str(exc_info.value)

    # Malformed IATA code (contains special characters)
    with pytest.raises(SettingsError) as exc_info:
        Settings(SCAN_ORIGINS="DE!")
    assert "Scan origins must be 3-letter alphabetical IATA airport codes" in str(exc_info.value)
