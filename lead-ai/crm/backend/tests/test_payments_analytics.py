"""Payments / collections analytics (`payments_analytics.py`)."""

from datetime import date

import pytest

import payments_analytics as pa

TODAY = date(2026, 10, 22)


def lead(total=100000, reg=20000, emis=None, reg_payments=None, enrolled_at="2026-09-05",
         assigned_to="Asha", lead_id="L1", name="Dr A"):
    return {
        "lead_id": lead_id, "id": 1, "full_name": name, "assigned_to": assigned_to,
        "actual_revenue": total, "registration_fees": reg, "emi_details": emis or [],
        "registration_payments": reg_payments, "enrolled_at": enrolled_at,
    }


def emi(due, amount=10000, status="pending", **extra):
    return {"date": due, "amount": amount, "status": status, **extra}


class TestFinanceFor:
    def test_collected_is_registration_plus_paid_emis(self):
        f = pa.finance_for(lead(emis=[emi("2026-09-01", 30000, "paid"), emi("2026-12-01", 50000)]), TODAY)
        assert f["collected"] == 50000 and f["balance"] == 50000 and f["status"] == "partial"

    def test_overdue_when_unpaid_and_past_due(self):
        f = pa.finance_for(lead(emis=[emi("2026-10-01", 10000), emi("2026-11-01", 10000)]), TODAY)
        assert f["overdue"] == 10000 and f["status"] == "overdue"

    def test_due_today_is_not_overdue(self):
        assert pa.finance_for(lead(emis=[emi("2026-10-22")]), TODAY)["overdue"] == 0

    def test_fully_paid(self):
        f = pa.finance_for(lead(total=50000, reg=50000), TODAY)
        assert f["status"] == "paid" and f["balance"] == 0

    def test_emi_details_may_be_a_json_string(self):
        l = lead()
        l["emi_details"] = '[{"date": "2026-10-01", "amount": 500, "status": "pending"}]'
        assert pa.finance_for(l, TODAY)["overdue"] == 500


class TestInPeriod:
    def test_uses_enrollment_day_never_updated_at(self):
        l = lead(enrolled_at=None)
        l["updated_at"] = "2026-09-20"
        assert not pa.in_period(l, "2026-09-01", "2026-09-30")

    def test_resolved_enroll_date_counts(self):
        l = lead(enrolled_at=None)
        l["enroll_date"] = "2026-09-12T10:00:00"
        assert pa.in_period(l, "2026-09-01", "2026-09-30")

    def test_bounds_inclusive_and_open_ended(self):
        l = lead(enrolled_at="2026-09-30T23:00:00+00:00")
        assert pa.in_period(l, "2026-09-01", "2026-09-30")
        assert not pa.in_period(l, "2026-10-01", None)
        assert pa.in_period(l, None, None)


class TestPaymentEvents:
    def test_dated_registration_payments(self):
        ev = pa.payment_events(lead(reg_payments=[{"date": "2026-09-09", "amount": 5000}, {"date": "2026-09-20", "amount": 15000}]))
        assert [(e["date"], e["amount"], e["approx"]) for e in ev] == [("2026-09-09", 5000, False), ("2026-09-20", 15000, False)]

    def test_registration_without_dates_falls_back_to_enrollment_day_flagged_approx(self):
        ev = pa.payment_events(lead())
        assert ev == [{"date": "2026-09-05", "amount": 20000.0, "kind": "registration", "approx": True}]

    def test_paid_emi_uses_paid_date_else_due_date_approx(self):
        ev = pa.payment_events(lead(reg=0, emis=[emi("2026-08-01", 100, "paid", paid_date="2026-08-05"), emi("2026-09-01", 200, "paid")]))
        assert (ev[0]["date"], ev[0]["approx"]) == ("2026-08-05", False)
        assert (ev[1]["date"], ev[1]["approx"]) == ("2026-09-01", True)

    def test_unpaid_emis_are_not_collections(self):
        assert pa.payment_events(lead(reg=0, emis=[emi("2026-08-01")])) == []


class TestCollectionsByMonth:
    def test_collected_vs_expected_per_month(self):
        leads = [lead(reg=10000, reg_payments=[{"date": "2026-09-02", "amount": 10000}],
                      emis=[emi("2026-10-05", 5000, "paid", paid_date="2026-10-06"), emi("2026-10-25", 7000)])]
        rows = {r["month"]: r for r in pa.collections_by_month(leads, "2026-10", 3)}
        assert rows["2026-09"]["collected"] == 10000
        assert rows["2026-10"]["collected"] == 5000
        assert rows["2026-10"]["expected"] == 12000  # both EMIs fall due in October

    def test_returns_requested_months_zero_filled(self):
        rows = pa.collections_by_month([], "2026-01", 3)
        assert [r["month"] for r in rows] == ["2025-11", "2025-12", "2026-01"]
        assert all(r["collected"] == 0 for r in rows)

    def test_approx_collected_reported(self):
        rows = pa.collections_by_month([lead()], "2026-09", 1)
        assert rows[0]["collected"] == 20000 and rows[0]["approx_collected"] == 20000


class TestOverdueAndAging:
    LEADS = [lead(emis=[emi("2026-10-20", 1000), emi("2026-10-01", 2000), emi("2026-07-01", 3000), emi("2026-12-01", 9999)])]

    def test_overdue_list_sorted_most_overdue_first(self):
        out = pa.overdue_emis(self.LEADS, TODAY)
        assert [o["days_overdue"] for o in out] == [113, 21, 2]
        assert out[0]["emi_index"] == 2 and out[0]["amount"] == 3000

    def test_aging_buckets(self):
        b = {r["bucket"]: r for r in pa.aging_buckets(pa.overdue_emis(self.LEADS, TODAY))}
        assert b["1-7 days"]["count"] == 1 and b["1-7 days"]["amount"] == 1000
        assert b["8-30 days"]["count"] == 1
        assert b["60+ days"]["amount"] == 3000
        assert b["31-60 days"]["count"] == 0

    def test_paid_emis_never_overdue(self):
        assert pa.overdue_emis([lead(emis=[emi("2026-01-01", 5, "paid")])], TODAY) == []


class TestDueSoon:
    def test_window_and_order(self):
        leads = [lead(emis=[emi("2026-10-25", 1), emi("2026-10-22", 2), emi("2026-12-30", 3), emi("2026-10-10", 4)])]
        out = pa.due_soon(leads, TODAY, 30)
        assert [o["days_until"] for o in out] == [0, 3]


class TestByCounselorAndSummary:
    def test_per_counselor_collection_rate(self):
        leads = [lead(total=100000, reg=50000, assigned_to="Asha"), lead(total=100000, reg=10000, assigned_to="Ravi", lead_id="L2")]
        rows = {r["counselor"]: r for r in pa.by_counselor(leads, TODAY)}
        assert rows["Asha"]["collection_rate"] == 50.0 and rows["Ravi"]["collection_rate"] == 10.0
        assert pa.by_counselor(leads, TODAY)[0]["counselor"] == "Asha"  # most collected first

    def test_summary_adds_up(self):
        s = pa.summary([lead(total=100000, reg=20000, emis=[emi("2026-10-01", 10000)])], TODAY)
        assert s["total"] == 100000 and s["collected"] == 20000 and s["balance"] == 80000
        assert s["overdue"] == 10000 and s["overdue_leads"] == 1 and s["collection_rate"] == 20.0

    def test_empty_summary(self):
        assert pa.summary([], TODAY)["collection_rate"] == 0.0


class TestDataQuality:
    def test_flags(self):
        dq = pa.data_quality([lead(total=0), lead(enrolled_at=None, lead_id="L2")])
        assert dq["missing_fee"] == 1 and dq["undated_enrollments"] == 1


class TestMarkEmiPaid:
    def test_marks_one_emi_without_mutating_input(self):
        original = [emi("2026-10-01"), emi("2026-11-01")]
        out = pa.mark_emi_paid(original, 1, "2026-10-22", "UPI", "Asha")
        assert out[1]["status"] == "paid" and out[1]["paid_date"] == "2026-10-22"
        assert out[1]["method"] == "UPI" and out[1]["paid_recorded_by"] == "Asha"
        assert original[1]["status"] == "pending" and out[0]["status"] == "pending"

    def test_double_pay_rejected(self):
        with pytest.raises(ValueError, match="already"):
            pa.mark_emi_paid([emi("2026-10-01", status="paid")], 0, "2026-10-22", None, None)

    @pytest.mark.parametrize("idx", [-1, 5])
    def test_bad_index_rejected(self, idx):
        with pytest.raises(ValueError, match="not found"):
            pa.mark_emi_paid([emi("2026-10-01")], idx, "2026-10-22", None, None)

    def test_bad_date_rejected(self):
        with pytest.raises(ValueError, match="date"):
            pa.mark_emi_paid([emi("2026-10-01")], 0, "nope", None, None)


class TestEmiNotifications:
    def test_one_overdue_and_one_due_soon_per_lead(self):
        l = lead(emis=[emi("2026-10-01", 1000), emi("2026-09-01", 2000), emi("2026-10-24", 500), emi("2027-01-01", 9)])
        notes = {n["kind"]: n for n in pa.emi_notifications([l], TODAY)}
        assert notes["emi_overdue"]["count"] == 2 and notes["emi_overdue"]["amount"] == 3000 and notes["emi_overdue"]["days"] == 51
        assert notes["emi_due"]["count"] == 1 and notes["emi_due"]["days"] == 2

    def test_nothing_when_all_paid_or_far_off(self):
        assert pa.emi_notifications([lead(emis=[emi("2026-10-01", status="paid"), emi("2027-05-01")])], TODAY) == []


def test_csv_rows_header_and_values():
    rows = pa.to_csv_rows([lead(total=100000, reg=20000)], TODAY)
    assert rows[0][0] == "Lead ID" and rows[1][4:] == [100000.0, 20000.0, 80000.0, 0.0, "partial"]


class TestActualAmountReceived:
    def test_paid_amount_defaults_to_scheduled_and_can_differ(self):
        assert pa.paid_amount(emi("2026-09-01", 1000, "paid")) == 1000
        assert pa.paid_amount(emi("2026-09-01", 1000, "paid", paid_amount=700)) == 700
        assert pa.paid_amount(emi("2026-09-01", 1000, "paid", paid_amount=0)) == 0

    def test_collected_and_balance_use_what_was_actually_received(self):
        f = pa.finance_for(lead(total=100000, reg=20000, emis=[emi("2026-09-01", 30000, "paid", paid_amount=25000)]), TODAY)
        assert f["collected"] == 45000 and f["balance"] == 55000

    def test_mark_paid_stores_actual_amount_only_when_given(self):
        out = pa.mark_emi_paid([emi("2026-10-01", 1000)], 0, "2026-10-22", None, None, 800)
        assert out[0]["paid_amount"] == 800
        assert "paid_amount" not in pa.mark_emi_paid([emi("2026-10-01", 1000)], 0, "2026-10-22", None, None)[0]
        with pytest.raises(ValueError, match="negative"):
            pa.mark_emi_paid([emi("2026-10-01", 1000)], 0, "2026-10-22", None, None, -5)

    def test_payment_event_uses_actual_amount(self):
        ev = pa.payment_events(lead(reg=0, emis=[emi("2026-08-01", 1000, "paid", paid_date="2026-08-03", paid_amount=600)]))
        assert ev[0]["amount"] == 600


class TestEmiMonthReport:
    LEADS = [
        lead(lead_id="L1", name="A", emis=[emi("2026-10-05", 10000, "paid", paid_date="2026-10-06", paid_amount=9000, method="UPI"),
                                           emi("2026-11-05", 10000)]),
        lead(lead_id="L2", name="B", emis=[emi("2026-10-01", 5000), emi("2026-10-28", 7000)]),
    ]

    def test_rows_for_the_due_month_with_status_and_amounts(self):
        rows = pa.emi_rows(self.LEADS, "2026-10", TODAY)
        assert [(r["name"], r["status"], r["scheduled"], r["received"]) for r in rows] == [
            ("B", "overdue", 5000, 0), ("A", "paid", 10000, 9000), ("B", "pending", 7000, 0)]
        paid = next(r for r in rows if r["status"] == "paid")
        assert paid["method"] == "UPI" and paid["paid_date"] == "2026-10-06" and paid["emi_count"] == 2

    def test_other_months_excluded(self):
        assert all(r["due_date"].startswith("2026-10") for r in pa.emi_rows(self.LEADS, "2026-10", TODAY))
        assert len(pa.emi_rows(self.LEADS, "2026-11", TODAY)) == 1

    def test_summary_scheduled_vs_received_and_shortfall(self):
        s = pa.emi_month_summary(pa.emi_rows(self.LEADS, "2026-10", TODAY))
        assert s["scheduled"] == 22000 and s["received"] == 9000
        assert s["shortfall"] == 1000          # paid 9000 against a scheduled 10000
        assert s["outstanding"] == 12000       # 5000 overdue + 7000 pending
        assert (s["paid_count"], s["pending_count"], s["overdue_count"]) == (1, 1, 1)
        assert s["overdue_amount"] == 5000 and s["collection_rate"] == 40.9

    def test_empty_month(self):
        s = pa.emi_month_summary([])
        assert s["count"] == 0 and s["collection_rate"] == 0.0

    def test_trend_by_due_month(self):
        t = {r["month"]: r for r in pa.emi_trend(self.LEADS, "2026-11", 3)}
        assert t["2026-10"]["scheduled"] == 22000 and t["2026-10"]["received"] == 9000
        assert t["2026-11"]["scheduled"] == 10000 and t["2026-11"]["received"] == 0
        assert t["2026-09"]["scheduled"] == 0 and t["2026-09"]["rate"] == 0.0


class TestDroppedStudents:
    EMIS = [emi("2026-08-01", 10000, "paid", paid_date="2026-08-02"), emi("2026-09-01", 10000), emi("2026-12-01", 10000)]

    def test_drop_cancels_only_unpaid_instalments_and_keeps_them_on_record(self):
        out, n, amt = pa.drop_emis(self.EMIS, "2026-10-10")
        assert (n, amt) == (2, 20000.0)
        assert [e["status"] for e in out] == ["paid", "cancelled", "cancelled"]
        assert out[1]["cancelled_on"] == "2026-10-10" and out[1]["cancelled_reason"] == "drop"
        assert self.EMIS[1]["status"] == "pending"            # input not mutated

    def test_cancelled_instalments_are_not_overdue_owed_or_scheduled(self):
        l = lead(emis=pa.drop_emis(self.EMIS, "2026-10-10")[0])
        assert pa.overdue_emis([l], TODAY) == []
        assert pa.finance_for(l, TODAY)["overdue"] == 0
        assert pa.due_soon([l], TODAY, 90) == []
        assert pa.emi_notifications([l], TODAY) == []
        assert pa.emi_rows([l], "2026-09", TODAY) == []
        assert {r["month"]: r["scheduled"] for r in pa.emi_trend([l], "2026-12", 6)}["2026-12"] == 0
        assert {r["month"]: r["expected"] for r in pa.collections_by_month([l], "2026-12", 6)}["2026-12"] == 0

    def test_paid_money_is_still_counted_after_a_drop(self):
        l = lead(reg=20000, emis=pa.drop_emis(self.EMIS, "2026-10-10")[0])
        assert pa.finance_for(l, TODAY)["collected"] == 30000   # registration + the one paid EMI

    def test_cancelled_instalment_cannot_be_marked_paid(self):
        out = pa.drop_emis(self.EMIS, "2026-10-10")[0]
        with pytest.raises(ValueError, match="cancelled"):
            pa.mark_emi_paid(out, 1, "2026-10-12", None, None)

    def test_open_emi_summary_is_what_a_drop_would_cancel(self):
        assert pa.open_emi_summary(self.EMIS) == {"count": 2, "amount": 20000.0}
        assert pa.open_emi_summary(pa.drop_emis(self.EMIS, "2026-10-10")[0]) == {"count": 0, "amount": 0.0}

    def test_restore_brings_back_only_what_the_drop_cancelled(self):
        mixed = [emi("2026-08-01", 5, "paid"), emi("2026-09-01", 5, "cancelled")]          # cancelled for some other reason
        dropped = pa.drop_emis(self.EMIS, "2026-10-10")[0] + mixed
        restored = pa.restore_emis(dropped)
        assert [e["status"] for e in restored] == ["paid", "pending", "pending", "paid", "cancelled"]
        assert "cancelled_on" not in restored[1]

    def test_dropping_a_student_with_nothing_unpaid(self):
        out, n, amt = pa.drop_emis([emi("2026-08-01", 10, "paid")], "2026-10-10")
        assert (n, amt) == (0, 0.0) and out[0]["status"] == "paid"
