"""Tests for client.py — OdooClient wrapping s6r_odoo + image helpers."""

import base64
import pickle
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


# ── Fixture: OdooClient with mocked s6r_odoo ─────────────────────────────────

@pytest.fixture
def mock_s6r(mocker):
    """Patch s6r_odoo.OdooConnection so no real connection is made."""
    mock = mocker.patch("odoo_configurator.client._S6rOdoo")
    instance = mock.return_value
    instance.context = {"lang": "fr_FR", "noupdate": True}
    instance.get_ref.return_value = 7
    instance.get_record.return_value = {"id": 7, "name": "Test"}
    instance.search_ids.return_value = [42]
    instance.get_country.return_value = 14
    instance.get_menu.return_value = 5
    instance.get_local_file.return_value = "file content"
    instance.get_xml_id_from_id.return_value = "external_config.partner_1"
    instance.get_id_from_xml_id.return_value = 99
    instance.default_get.return_value = False
    return instance


@pytest.fixture
def client(mock_s6r):
    from odoo_configurator.client import OdooClient
    return OdooClient(url="http://localhost", db="test", user="admin", password="admin")


# ── Delegation to s6r_odoo ────────────────────────────────────────────────────

def test_get_ref_delegates(client, mock_s6r):
    result = client.get_ref("base.EUR")
    mock_s6r.get_ref.assert_called_once_with("base.EUR")
    assert result == 7


def test_get_record_delegates(client, mock_s6r):
    result = client.get_record("res.partner", 7)
    mock_s6r.get_record.assert_called_once_with("res.partner", 7, context=None)
    assert result["name"] == "Test"


def test_get_search_id_returns_first(client, mock_s6r):
    mock_s6r.search_ids.return_value = [42, 43]
    result = client.get_search_id("res.partner", [("name", "=", "ACME")])
    assert result == 42


def test_get_search_id_returns_none_when_empty(client, mock_s6r):
    mock_s6r.search_ids.return_value = []
    result = client.get_search_id("res.partner", [("name", "=", "MISSING")])
    assert result is None


def test_get_country_delegates(client, mock_s6r):
    result = client.get_country("FR")
    mock_s6r.get_country.assert_called_once_with("FR")
    assert result == 14


def test_get_menu_delegates(client, mock_s6r):
    result = client.get_menu(1, "/about")
    mock_s6r.get_menu.assert_called_once_with(1, "/about")
    assert result == 5


def test_get_local_file_delegates(client, mock_s6r):
    result = client.get_local_file("/path/to/file.txt")
    mock_s6r.get_local_file.assert_called_once_with("/path/to/file.txt", encode=False)
    assert result == "file content"


def test_get_xml_id_from_id_delegates(client, mock_s6r):
    result = client.get_xml_id_from_id("res.partner", 1)
    mock_s6r.get_xml_id_from_id.assert_called_once_with("res.partner", 1)
    assert result == "external_config.partner_1"


def test_get_id_from_xml_id_delegates(client, mock_s6r):
    result = client.get_id_from_xml_id("external_config.partner_1")
    mock_s6r.get_id_from_xml_id.assert_called_once_with("external_config.partner_1", no_raise=False)
    assert result == 99


def test_default_get_delegates(client, mock_s6r):
    client.default_get("res.partner", "country_id")
    mock_s6r.default_get.assert_called_once_with("res.partner", "country_id")


def test_context_property(client, mock_s6r):
    assert client.context == {"lang": "fr_FR", "noupdate": True}


def test_odoo_attribute_is_s6r_instance(client, mock_s6r):
    """client.odoo gives direct access to the raw s6r_odoo instance."""
    assert client.odoo is mock_s6r


# ── create_xml_id ─────────────────────────────────────────────────────────────

def test_create_xml_id_sanitises_name(client, mock_s6r):
    client.create_xml_id("external_config", "res.partner", "My Partner Name!", 42)
    mock_s6r.create.assert_called_once_with("ir.model.data", {
        "module": "external_config",
        "name": "my_partner_name_",
        "model": "res.partner",
        "res_id": 42,
    })


# ── get_image_local ───────────────────────────────────────────────────────────

def test_get_image_local_encodes_file(client, tmp_path):
    img = tmp_path / "logo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nFAKEDATA")
    result = client.get_image_local(str(img))
    expected = base64.b64encode(b"\x89PNG\r\n\x1a\nFAKEDATA").decode("utf-8")
    assert result == expected


# ── get_image_url ─────────────────────────────────────────────────────────────

def test_get_image_url_downloads_and_encodes(client, tmp_path, mocker):
    mocker.patch("odoo_configurator.client._IMAGE_CACHE_PATH", tmp_path / "img_cache")
    client._image_cache = {}

    fake_content = b"PNGDATA"
    mock_response = MagicMock()
    mock_response.content = fake_content
    mock_get = mocker.patch("odoo_configurator.client.requests.get", return_value=mock_response)

    result = client.get_image_url("https://example.com/logo.png")

    mock_get.assert_called_once_with("https://example.com/logo.png", timeout=30)
    mock_response.raise_for_status.assert_called_once()
    assert result == base64.b64encode(fake_content).decode("utf-8")


def test_get_image_url_uses_cache_on_second_call(client, tmp_path, mocker):
    mocker.patch("odoo_configurator.client._IMAGE_CACHE_PATH", tmp_path / "img_cache")
    # Reset the in-memory cache so a stale on-disk cache from another test doesn't interfere.
    client._image_cache = {}

    fake_content = b"PNGDATA"
    mock_response = MagicMock()
    mock_response.content = fake_content
    mock_get = mocker.patch("odoo_configurator.client.requests.get", return_value=mock_response)

    url = "https://example.com/logo.png"
    client.get_image_url(url)
    client.get_image_url(url)  # second call

    # requests.get should only be called once — second call hits the in-memory cache
    assert mock_get.call_count == 1


def test_get_image_url_cache_persisted_and_restored(client, tmp_path, mocker):
    """After a download the cache is pickled; on next client init it's restored."""
    cache_file = tmp_path / "img_cache"
    mocker.patch("odoo_configurator.client._IMAGE_CACHE_PATH", cache_file)

    fake_content = b"IMGDATA"
    mock_response = MagicMock()
    mock_response.content = fake_content
    mocker.patch("odoo_configurator.client.requests.get", return_value=mock_response)

    url = "https://example.com/img.png"
    client.get_image_url(url)

    assert cache_file.is_file()

    # Simulate a fresh client loading the cache
    from odoo_configurator.client import OdooClient
    client2 = OdooClient.__new__(OdooClient)
    client2._image_cache = client2._load_image_cache()  # uses the patched path
    assert url in client2._image_cache
