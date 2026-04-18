"""
pytest 공통 픽스처

PySide6 GUI가 없는 순수 유닛 테스트를 지원하기 위해
sys.path에 프로젝트 루트를 등록합니다.
"""
import sys
import os
import json
import pytest

# 프로젝트 루트를 경로에 추가 (version.py, app/ 패키지 모두 인식)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def tmp_settings_file(tmp_path, monkeypatch):
    """임시 경로를 사용하는 설정 파일 픽스처.
    실제 APPDATA 설정 파일을 건드리지 않고 load/save_settings를 테스트할 수 있습니다."""
    import app.core.config as cfg

    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(cfg, "SETTINGS_FILE", settings_path)
    monkeypatch.setattr(cfg, "_settings_cache", None)
    yield settings_path
    monkeypatch.setattr(cfg, "_settings_cache", None)
