"""Tests for evaluator.py — expression resolution against the eval namespace."""

import pytest
from unittest.mock import MagicMock
from odoo_configurator.evaluator import (
    make_eval_ns,
    resolve_value,
    resolve_dict,
    resolve_deep,
    eval_domain,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_ref.return_value = 7
    client.get_country.return_value = 14
    client.get_search_id.return_value = 42
    client.get_image_local.return_value = "base64data=="
    return client


@pytest.fixture
def mock_secrets():
    secrets = MagicMock()
    secrets.get_env_var.return_value = "env_value"
    return secrets


@pytest.fixture
def mock_utils():
    utils = MagicMock()
    utils.resolve_path.return_value = "/abs/path/file.csv"
    return utils


@pytest.fixture
def ns(mock_client, mock_secrets, mock_utils):
    return make_eval_ns(mock_client, mock_secrets, mock_utils)


# ── resolve_value — literals ──────────────────────────────────────────────────

def test_literal_string_untouched(ns):
    assert resolve_value("Partner Name", ns) == "Partner Name"


def test_literal_int_untouched(ns):
    assert resolve_value(42, ns) == 42


def test_literal_bool_untouched(ns):
    assert resolve_value(True, ns) is True


def test_literal_none_untouched(ns):
    assert resolve_value(None, ns) is None


def test_literal_dict_untouched(ns):
    d = {"key": "val"}
    assert resolve_value(d, ns) is d  # same object, not resolved


def test_bare_get_name_without_parens_raises(ns):
    """
    A string like 'get_foo' (no parens) starts with 'get_' so it is passed to eval
    as a name lookup. If it's not in the namespace, NameError is raised.
    YAML values that start with 'get_' must always be function calls: get_foo(...).
    """
    with pytest.raises(NameError):
        resolve_value("get_this_is_not_a_function_call", ns)


def test_get_expression_evaluated(ns, mock_client):
    result = resolve_value("get_ref('base.EUR')", ns)
    mock_client.get_ref.assert_called_once_with("base.EUR")
    assert result == 7


def test_get_country_evaluated(ns, mock_client):
    result = resolve_value("get_country('FR')", ns)
    mock_client.get_country.assert_called_once_with("FR")
    assert result == 14


def test_get_env_var_evaluated(ns, mock_secrets):
    result = resolve_value("get_env_var('MY_VAR')", ns)
    mock_secrets.get_env_var.assert_called_once_with("MY_VAR")
    assert result == "env_value"


def test_unknown_get_function_raises_name_error(ns):
    with pytest.raises(NameError) as exc_info:
        resolve_value("get_nonexistent('foo')", ns)
    assert "get_nonexistent" in str(exc_info.value)
    assert "Available get_*" in str(exc_info.value)


def test_arbitrary_python_blocked(ns):
    """__builtins__ is disabled — arbitrary Python cannot be executed."""
    with pytest.raises((NameError, TypeError)):
        resolve_value("get_ref(__import__('os').getcwd())", ns)


# ── Nested calls via 'o' (legacy syntax) ─────────────────────────────────────

def test_nested_o_syntax(ns, mock_client):
    """get_search_id('model', [('id', '=', o.get_ref('base.x'))]) should work."""
    mock_client.get_ref.return_value = 5
    mock_client.get_search_id.return_value = 99

    result = resolve_value(
        "get_search_id('res.partner', [('id', '=', o.get_ref('base.x'))], 'asc')",
        ns
    )
    assert result == 99
    mock_client.get_ref.assert_called_once_with("base.x")


# ── resolve_dict ──────────────────────────────────────────────────────────────

def test_resolve_dict_resolves_get_values(ns, mock_client):
    d = {"name": "ACME", "country_id": "get_country('US')", "active": True}
    result = resolve_dict(d, ns)
    assert result["name"] == "ACME"
    assert result["country_id"] == 14
    assert result["active"] is True
    mock_client.get_country.assert_called_once_with("US")


def test_resolve_dict_does_not_mutate_input(ns):
    original = {"country_id": "get_country('FR')"}
    resolve_dict(original, ns)
    assert original["country_id"] == "get_country('FR')"  # original unchanged


def test_resolve_dict_empty(ns):
    assert resolve_dict({}, ns) == {}


# ── resolve_deep ──────────────────────────────────────────────────────────────

def test_resolve_deep_nested_dict(ns, mock_client):
    data = {"outer": {"inner": "get_ref('base.EUR')"}}
    result = resolve_deep(data, ns)
    assert result["outer"]["inner"] == 7


def test_resolve_deep_list(ns, mock_client):
    data = ["get_ref('base.EUR')", "literal", 42]
    result = resolve_deep(data, ns)
    assert result == [7, "literal", 42]


def test_resolve_deep_list_of_tuples(ns):
    """Domain-style lists with mixed content."""
    data = [("name", "=", "test"), ("active", "=", True)]
    result = resolve_deep(data, ns)
    assert result == [("name", "=", "test"), ("active", "=", True)]


# ── eval_domain ───────────────────────────────────────────────────────────────

def test_eval_domain_already_list(ns):
    domain = [("name", "=", "test")]
    result = eval_domain(domain, ns)
    assert result == [("name", "=", "test")]


def test_eval_domain_string_literal(ns):
    domain = "[('name', '=', 'test')]"
    result = eval_domain(domain, ns)
    assert result == [("name", "=", "test")]


def test_eval_domain_string_with_get_ref(ns, mock_client):
    mock_client.get_ref.return_value = 5
    domain = "[('partner_id', '=', get_ref('base.partner_demo'))]"
    result = eval_domain(domain, ns)
    assert result == [("partner_id", "=", 5)]


def test_eval_domain_wrong_type_raises(ns):
    with pytest.raises(TypeError, match="list or string"):
        eval_domain(42, ns)


# ── make_eval_ns structure ────────────────────────────────────────────────────

def test_ns_contains_expected_functions(mock_client, mock_secrets, mock_utils):
    ns = make_eval_ns(mock_client, mock_secrets, mock_utils)
    expected = [
        "get_ref", "get_record", "get_search_id", "get_country", "get_menu",
        "get_image_url", "get_image_local", "get_local_file",
        "get_xml_id_from_id", "get_default", "get_env_var",
    ]
    for name in expected:
        assert name in ns, f"'{name}' missing from eval namespace"


def test_ns_contains_legacy_o_object(mock_client, mock_secrets, mock_utils):
    ns = make_eval_ns(mock_client, mock_secrets, mock_utils)
    assert ns["o"] is mock_client


def test_ns_builtins_disabled(mock_client, mock_secrets, mock_utils):
    ns = make_eval_ns(mock_client, mock_secrets, mock_utils)
    assert ns["__builtins__"] == {}
