"""Report templates are editable in the admin, so the PDF engine must not
read local files or reach the network for them."""
import pytest

from apps.reports.render import embedded_only_fetcher, pdf_engine_available

pytestmark = pytest.mark.skipif(not pdf_engine_available(), reason="WeasyPrint system libraries not installed")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://169.254.169.254/latest/meta-data/",
    "https://example.com/logo.png",
    "FILE:///etc/passwd",
])
def test_only_embedded_resources_are_fetched(url):
    with pytest.raises(ValueError):
        embedded_only_fetcher().fetch(url)


def test_embedded_images_still_load():
    response = embedded_only_fetcher().fetch("data:text/plain;base64,aGk=")
    assert response.read() == b"hi"
