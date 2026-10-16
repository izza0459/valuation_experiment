import pytest


@pytest.fixture(autouse=True)
def _real_rules(settings):
    """Tests check the full rules; demo mode is tested on its own."""
    settings.DEMO_MODE = False


@pytest.fixture(autouse=True)
def _isolated_media_root(settings, tmp_path):
    """Uploaded files go to a throwaway folder, never into the project's `media/`."""
    settings.MEDIA_ROOT = tmp_path / "media"
