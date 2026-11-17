"""Server-side tallies that replace the Analytics page counting 10,000 leads in the browser."""

import analytics_breakdown as ab


def lead(owner, status, source="Meta", course="MD", fee=0):
    return {"assigned_to": owner, "status": status, "source": source, "course_interested": course, "actual_revenue": fee}


def test_counts_every_status_and_books_revenue_on_enrolled_only():
    rows = ab.counselor_rows([
        lead("Asha", "Enrolled", fee=50000), lead("Asha", "Hot", fee=99999), lead("Asha", "Junk"),
        lead("Asha", "Dropped"), lead("Ravi", "Fresh"),
    ])
    a = next(r for r in rows if r["name"] == "Asha")
    assert (a["total"], a["enrolled"], a["hot"], a["junk"], a["other"]) == (4, 1, 1, 1, 1)
    assert a["revenue"] == 50000 and a["lost"] == 1 and a["active"] == 1
    assert a["conversionRate"] == "25.0"
    assert rows[0]["name"] == "Asha"  # biggest first


def test_unassigned_leads_are_skipped_in_the_counselor_table_but_counted_in_totals():
    out = ab.breakdown([lead(None, "Fresh"), lead("Ravi", "Fresh")])
    assert out["total"] == 2 and [c["name"] for c in out["counselors"]] == ["Ravi"]


def test_source_and_course_tallies_skip_blanks_and_sort_by_count():
    leads = [lead("A", "Fresh", "Meta", "MD"), lead("A", "Fresh", "Meta", ""), lead("A", "Fresh", " Web ", "MD"),
             lead("A", "Fresh", None, None)]
    assert ab.tally(leads, "source") == [{"name": "Meta", "count": 2}, {"name": "Web", "count": 1}]
    assert ab.tally(leads, "course_interested") == [{"name": "MD", "count": 2}]


def test_empty_input():
    assert ab.breakdown([]) == {"total": 0, "counselors": [], "sources": [], "courses": []}
