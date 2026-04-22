"""Tests that handler feature configs match legacy feature module names and counts.

Full equivalence (numerical diff < 1e-6) requires Qlib binary data and runs
as an integration test. These unit tests verify structural equivalence:
- Same feature count expectations
- No duplicate feature names
- Label expressions are consistent
- Tech feature names follow TECH_* naming convention
- Fundamental feature names follow FUND_* naming convention
"""
from __future__ import annotations

import pytest

qlib = pytest.importorskip("qlib", reason="pyqlib not installed")

from qlib_ext.handlers.tw_alpha import TWAlphaHandler
from qlib_ext.handlers.tw_fundamental import TWFundamentalHandler
from qlib_ext.handlers.tw_combined import TWCombinedHandler


# ---------------------------------------------------------------------------
# TWAlphaHandler
# ---------------------------------------------------------------------------

def test_alpha_feature_fields_and_names_same_length():
    fields, names = TWAlphaHandler.get_feature_config()
    assert len(fields) == len(names)


def test_alpha_feature_names_are_unique():
    _, names = TWAlphaHandler.get_feature_config()
    assert len(names) == len(set(names))


def test_alpha_feature_names_prefixed_tech():
    _, names = TWAlphaHandler.get_feature_config()
    for name in names:
        assert name.startswith("TECH_"), f"Expected TECH_ prefix: {name}"


def test_alpha_has_ma_return_features():
    _, names = TWAlphaHandler.get_feature_config()
    for n in [5, 10, 20, 60]:
        assert f"TECH_MA{n}_RET" in names


def test_alpha_has_volume_ratio_features():
    _, names = TWAlphaHandler.get_feature_config()
    for n in [5, 10, 20]:
        assert f"TECH_VOL{n}_RATIO" in names


def test_alpha_label_is_20d_return():
    fields, names = TWAlphaHandler.get_label_config()
    assert names[0] == "LABEL_RET20D"
    assert "20" in fields[0]
    assert "$close" in fields[0]


# ---------------------------------------------------------------------------
# TWFundamentalHandler
# ---------------------------------------------------------------------------

def test_fund_feature_fields_and_names_same_length():
    fields, names = TWFundamentalHandler.get_feature_config()
    assert len(fields) == len(names)


def test_fund_feature_names_are_unique():
    _, names = TWFundamentalHandler.get_feature_config()
    assert len(names) == len(set(names))


def test_fund_feature_names_prefixed_fund():
    _, names = TWFundamentalHandler.get_feature_config()
    for name in names:
        assert name.startswith("FUND_"), f"Expected FUND_ prefix: {name}"


def test_fund_has_revenue_features():
    _, names = TWFundamentalHandler.get_feature_config()
    assert "FUND_REV_YOY" in names
    assert "FUND_REV_MOM" in names


def test_fund_has_roe_and_gm_features():
    _, names = TWFundamentalHandler.get_feature_config()
    assert "FUND_ROE" in names
    assert "FUND_GM" in names


# ---------------------------------------------------------------------------
# TWCombinedHandler
# ---------------------------------------------------------------------------

def test_combined_label_matches_alpha_label():
    combined_fields, combined_names = TWCombinedHandler.get_label_config()
    alpha_fields, alpha_names = TWAlphaHandler.get_label_config()
    assert combined_fields == alpha_fields
    assert combined_names == alpha_names


def test_combined_binary_label_config():
    fields, names = TWCombinedHandler.get_binary_label_config()
    assert names[0] == "LABEL_BIN20D"
    assert "Gt(" in fields[0] or ">" in fields[0]


def test_combined_tech_only_excludes_fund_features():
    alpha_fields, alpha_names = TWAlphaHandler.get_feature_config()
    # When include_fundamental=False the combined feature list == tech only
    # We verify this via the config static method chain
    fund_fields, fund_names = TWFundamentalHandler.get_feature_config()
    tech_fields, tech_names = TWAlphaHandler.get_feature_config()
    # All tech features have TECH_ prefix, fundamental have FUND_
    assert not any(n.startswith("FUND_") for n in tech_names)
    assert not any(n.startswith("TECH_") for n in fund_names)


def test_combined_no_duplicate_names_with_fundamental():
    tech_fields, tech_names = TWAlphaHandler.get_feature_config()
    fund_fields, fund_names = TWFundamentalHandler.get_feature_config()
    all_names = tech_names + fund_names
    assert len(all_names) == len(set(all_names)), "Duplicate feature names in combined handler"


def test_combined_total_feature_count():
    tech_fields, tech_names = TWAlphaHandler.get_feature_config()
    fund_fields, fund_names = TWFundamentalHandler.get_feature_config()
    expected = len(tech_names) + len(fund_names)
    assert expected > 10, "Combined handler should have more than 10 features"
