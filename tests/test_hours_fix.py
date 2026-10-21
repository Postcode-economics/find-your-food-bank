import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from hours_fix import fix_span, fix_hours, bad_spans, phone_ok
def test_close_before_open_gets_pm():
    assert fix_span("09:30 - 05:00") == "09:30 - 17:00"
    assert fix_span("12:00 - 08:30") == "12:00 - 20:30"
    assert fix_span("12:00 - 04:00") == "12:00 - 16:00"
    assert fix_span("10:30 - 01:30") == "10:30 - 13:30"
    assert fix_span("07:45 - 05:00") == "07:45 - 17:00"
def test_both_pm_when_open_is_small_hours():
    assert fix_span("01:30 - 07:00") == "13:30 - 19:00"
    assert fix_span("04:30 - 06:00") == "16:30 - 18:00"
    assert fix_span("06:30 - 09:00") == "18:30 - 21:00"
def test_equal_is_ambiguous_and_gets_pm():
    assert fix_span("09:00 - 09:00") == "09:00 - 21:00"
def test_placeholders_and_unreadable_dropped():
    assert fix_span("00:00 - 00:00") is None
    assert fix_span("20:00 - 14:00") is None
def test_good_spans_untouched():
    for s in ["09:30 - 17:00", "13:00 - 15:00", "18:30 - 20:00", "10:00 - 12:30 Monthly", "08:00 - 09:00"]:
        assert fix_span(s) == s
    assert fix_span("Lunchtime") == "Lunchtime"
def test_overnight_shelter_kept():
    assert fix_span("20:00 - 08:00", allow_overnight=True) == "20:00 - 08:00"
def test_fix_hours_dict_multi_span():
    h, ch = fix_hours({"Mon": "09:00 - 12:00 / 01:00 - 03:00", "Tue": "00:00 - 00:00", "Wed": "09:30 - 05:00 Monthly"})
    assert h == {"Mon": "09:00 - 12:00 / 13:00 - 15:00", "Wed": "09:30 - 17:00 Monthly"}
    assert len(ch) == 3 and bad_spans(h) == []
def test_meeting_centre_feed_values():
    # Warm Welcome feed had Tue 12:30-03:30 (1-3pm on the council page); the generic rule gets the pm right,
    # the source-derived override (overrides/warmspaces_verified.json) then sets the exact council times.
    assert fix_span("12:30 - 03:30") == "12:30 - 15:30"
def test_phone_needs_ten_digits():
    assert not phone_ok("020") and not phone_ok("") and phone_ok("020 7078 7899") and phone_ok("0117 924 4604")
def test_feed_separator_junk_normalised():
    h, _ = fix_hours({"Mon": "12:00 - 15.00", "Fri": "12:00 - 1500", "Thu": "Closed / 10:30 - 12:00"})
    assert h == {"Mon": "12:00 - 15:00", "Fri": "12:00 - 15:00", "Thu": "10:30 - 12:00"}
