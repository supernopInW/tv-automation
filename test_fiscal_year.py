"""Offline fiscal-year mapping tests for Workflow 26 month/year selection."""

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("APP_USER_REDIS_URI", "memory://")

import app as app_module
import automate_submission as cli


def test_thai_fiscal_year_be_oct_dec_rolls_forward():
    assert app_module.thai_fiscal_year_be(2568, 10) == 2569
    assert app_module.thai_fiscal_year_be(2568, 12) == 2569
    assert app_module.thai_fiscal_year_be(2569, 1) == 2569
    assert app_module.thai_fiscal_year_be(2569, 9) == 2569


def test_calendar_year_for_fiscal_sheet_oct():
    assert app_module.calendar_year_be_for_fiscal_sheet(2569, 10) == 2568
    assert app_module.calendar_year_be_for_fiscal_sheet(2569, 8) == 2569


def test_resolve_portal_fiscal_year_prefers_record_dates():
    # Legacy auto-plan sheet ตค68 + calendar dates → fiscal 2569
    records = [{"date": "05/10/2568"}]
    assert app_module.resolve_portal_fiscal_year("2568", 10, records) == "2569"
    # Sheet already fiscal, same dates
    assert app_module.resolve_portal_fiscal_year("2569", 10, records) == "2569"
    # No records: trust sheet fiscal suffix
    assert app_module.resolve_portal_fiscal_year("2569", 10, []) == "2569"


def test_month_label_from_full_sheet_name():
    assert app_module._month_name_thai_from_sheet("ตุลาคม69") == "ตุลาคม"
    assert app_module._month_name_thai_from_sheet("ตค69") == "ตุลาคม"
    assert app_module._month_name_thai_from_sheet("สค69") == "สิงหาคม"


def test_cli_helpers_match_backend():
    assert cli.thai_fiscal_year_be(2568, 10) == 2569
    assert cli.calendar_year_be_for_fiscal_sheet(2569, 10) == 2568
    assert cli.resolve_portal_fiscal_year("2568", 10, [{"date": "01/10/2568"}]) == "2569"


if __name__ == "__main__":
    for test in (
        test_thai_fiscal_year_be_oct_dec_rolls_forward,
        test_calendar_year_for_fiscal_sheet_oct,
        test_resolve_portal_fiscal_year_prefers_record_dates,
        test_month_label_from_full_sheet_name,
        test_cli_helpers_match_backend,
    ):
        test()
        print(f"PASS {test.__name__}")
