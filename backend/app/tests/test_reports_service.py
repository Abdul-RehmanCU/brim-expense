import types

from app.schemas.reports import ReportGenerateRequest
from app.schemas.review_queue import CitedPolicyClause
from app.services import reports_service


def test_generate_report_creates_report_and_items(monkeypatch):
    client = FakeSupabaseClient(
        {
            "employees": [
                {
                    "id": "employee_1",
                    "department_id": "department_1",
                    "full_name": "Sarah Chen",
                    "email": "sarah@example.com",
                    "role": "Marketing Lead",
                }
            ],
            "departments": [{"id": "department_1", "name": "Marketing", "manager_name": "Maya Singh"}],
            "transactions": [
                transaction("txn_1", "2026-05-01", "AIR CANADA", 420.15, "Travel"),
                transaction("txn_2", "2026-05-03", "HOTEL", 300, "Lodging"),
            ],
            "policy_checks": [
                {"id": "policy_1", "transaction_id": "txn_1", "status": "compliant", "created_at": "2026-05-02T00:00:00Z"},
                {
                    "id": "policy_2",
                    "transaction_id": "txn_2",
                    "status": "approval_evidence_needed",
                    "missing_information": ["preapproval"],
                    "created_at": "2026-05-04T00:00:00Z",
                },
            ],
            "risk_scores": [{"id": "risk_1", "transaction_id": "txn_2", "risk_level": "high", "created_at": "2026-05-04T00:00:00Z"}],
            "receipts": [{"id": "receipt_1", "transaction_id": "txn_1", "status": "submitted", "created_at": "2026-05-02T00:00:00Z"}],
            "preapprovals": [{"id": "pre_1", "transaction_id": "txn_2", "status": "missing", "created_at": "2026-05-04T00:00:00Z"}],
            "approval_requests": [{"id": "approval_1", "transaction_id": "txn_2", "status": "requested", "created_at": "2026-05-04T00:00:00Z"}],
            "expense_reports": [],
            "expense_report_items": [],
        }
    )
    monkeypatch.setattr(reports_service, "get_supabase_client", lambda: client)

    report = reports_service.generate_report(ReportGenerateRequest(request="Generate Sarah Chen report"))

    assert report.employee_name == "Sarah Chen"
    assert report.report_name == "Sarah Chen Expense Report"
    assert report.department_id == "department_1"
    assert report.item_count == 2
    assert report.total_amount_cad == 720.15
    assert report.missing_preapproval_count == 1
    assert report.open_approval_count == 1
    assert report.policy_flag_count == 1
    assert report.risk_flag_count == 1
    assert report.approval_ready is False
    assert report.visuals[0].title == "Spend by category"
    assert report.line_items[1].preapproval_status == "missing"
    assert report.line_items[1].approval_status == "requested"
    assert len(client.tables["expense_reports"]) == 1
    assert len(client.tables["expense_report_items"]) == 2
    assert client.tables["expense_report_items"][1]["policy_status"] == "approval_evidence_needed"


def test_generate_reports_keeps_department_prompt_as_one_aggregate_report(monkeypatch):
    client = FakeSupabaseClient(
        {
            "employees": [
                {
                    "id": "employee_1",
                    "department_id": "department_1",
                    "full_name": "Sarah Chen",
                    "email": "sarah@example.com",
                    "role": "Marketing Lead",
                },
                {
                    "id": "employee_2",
                    "department_id": "department_1",
                    "full_name": "Leo Kim",
                    "email": "leo@example.com",
                    "role": "Marketing Manager",
                },
            ],
            "departments": [{"id": "department_1", "name": "Marketing", "manager_name": "Maya Singh"}],
            "transactions": [
                transaction("txn_1", "2026-05-01", "AIR CANADA", 420.15, "Travel", employee_id="employee_1"),
                transaction("txn_2", "2026-05-03", "HOTEL", 300, "Lodging", employee_id="employee_1"),
                transaction("txn_3", "2026-05-05", "UBER", 40, "Ground Transportation", employee_id="employee_2"),
            ],
            "policy_checks": [],
            "risk_scores": [],
            "receipts": [],
            "preapprovals": [],
            "approval_requests": [],
            "expense_reports": [],
            "expense_report_items": [],
        }
    )
    monkeypatch.setattr(reports_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(reports_service, "plan_report_request_with_ai", lambda *_args, **_kwargs: None)

    response = reports_service.generate_reports(
        ReportGenerateRequest(request="Generate Sarah Chen expense report and the Marketing Team's")
    )

    assert response.generated_count == 2
    assert [report.report_name for report in response.reports] == ["Sarah Chen Expense Report", "Marketing Team Report"]
    assert response.targets[1].scope_type == "department"
    assert response.targets[1].report_count == 1
    assert "lower(d.name) in ('marketing')" in (response.sql_preview or "")
    assert len(client.tables["expense_reports"]) == 2
    assert response.reports[1].item_count == 3
    assert response.reports[1].total_amount_cad == 760.15
    assert response.reports[1].report_scope_type == "department"
    assert response.reports[1].visuals[0].title == "Spend per employee"
    assert [row.label for row in response.reports[1].visuals[0].rows] == ["Sarah Chen", "Leo Kim"]


def test_get_report_labels_multi_employee_department_report_as_team(monkeypatch):
    client = FakeSupabaseClient(
        {
            "employees": [
                {"id": "employee_1", "department_id": "department_1", "full_name": "Sarah Chen"},
                {"id": "employee_2", "department_id": "department_1", "full_name": "Leo Kim"},
            ],
            "departments": [{"id": "department_1", "name": "Marketing"}],
            "transactions": [
                transaction("txn_1", "2026-05-01", "AIR CANADA", 420.15, "Travel", employee_id="employee_1"),
                transaction("txn_2", "2026-05-05", "UBER", 40, "Ground Transportation", employee_id="employee_2"),
            ],
            "policy_checks": [],
            "risk_scores": [],
            "receipts": [],
            "preapprovals": [],
            "approval_requests": [],
            "expense_reports": [
                {
                    "id": "report_team",
                    "employee_id": "employee_1",
                    "department_id": "department_1",
                    "report_name": "Marketing Team Report",
                    "report_spec": {
                        "title": "Marketing Team Report",
                        "summary": "Department-level expense report with spending grouped by employee.",
                        "visuals": [
                            {
                                "id": "spend_per_employee",
                                "title": "Spend per employee",
                                "subtitle": "How total spend is distributed across the team.",
                                "chart_type": "bar",
                                "dimension": "employee",
                                "metric": "sum_amount_cad",
                                "limit": 12,
                                "sort_direction": "desc",
                            }
                        ],
                    },
                    "period_start": "2026-05-01",
                    "period_end": "2026-05-31",
                    "status": "generated",
                    "total_amount_cad": 460.15,
                    "missing_receipt_count": 0,
                    "policy_flag_count": 0,
                    "risk_flag_count": 0,
                    "ai_summary": "Marketing Team report.",
                }
            ],
            "expense_report_items": [
                {
                    "id": "item_1",
                    "report_id": "report_team",
                    "transaction_id": "txn_1",
                    "amount_cad": 420.15,
                    "category": "Travel",
                    "policy_status": "compliant",
                    "risk_level": "low",
                    "created_at": "2026-05-02T00:00:00Z",
                },
                {
                    "id": "item_2",
                    "report_id": "report_team",
                    "transaction_id": "txn_2",
                    "amount_cad": 40,
                    "category": "Ground Transportation",
                    "policy_status": "compliant",
                    "risk_level": "low",
                    "created_at": "2026-05-06T00:00:00Z",
                },
            ],
        }
    )
    monkeypatch.setattr(reports_service, "get_supabase_client", lambda: client)

    report = reports_service.get_report("report_team")

    assert report.employee_name == "Sarah Chen"
    assert report.report_name == "Marketing Team Report"
    assert report.department_name == "Marketing"
    assert report.item_count == 2
    assert report.report_scope_type == "department"
    assert report.visuals[0].rows[0].label == "Sarah Chen"


def test_export_report_csv_includes_totals_and_line_items(monkeypatch):
    client = FakeSupabaseClient(
        {
            "employees": [{"id": "employee_1", "department_id": "department_1", "full_name": "Sarah Chen"}],
            "departments": [{"id": "department_1", "name": "Marketing"}],
            "transactions": [transaction("txn_1", "2026-05-01", "AIR CANADA", 420.15, "Travel")],
            "policy_checks": [{"id": "policy_1", "transaction_id": "txn_1", "status": "approval_evidence_needed", "created_at": "2026-05-02T00:00:00Z"}],
            "risk_scores": [{"id": "risk_1", "transaction_id": "txn_1", "risk_level": "low", "created_at": "2026-05-02T00:00:00Z"}],
            "receipts": [{"id": "receipt_1", "transaction_id": "txn_1", "status": "submitted", "created_at": "2026-05-02T00:00:00Z"}],
            "preapprovals": [{"id": "pre_1", "transaction_id": "txn_1", "status": "missing", "created_at": "2026-05-02T00:00:00Z"}],
            "approval_requests": [{"id": "approval_1", "transaction_id": "txn_1", "status": "requested", "created_at": "2026-05-02T00:00:00Z"}],
            "expense_reports": [
                {
                    "id": "report_1",
                    "employee_id": "employee_1",
                    "department_id": "department_1",
                    "period_start": "2026-05-01",
                    "period_end": "2026-05-31",
                    "status": "generated",
                    "total_amount_cad": 420.15,
                    "missing_receipt_count": 0,
                    "policy_flag_count": 1,
                    "risk_flag_count": 0,
                    "ai_summary": "One transaction.",
                }
            ],
            "expense_report_items": [
                {
                    "id": "item_1",
                    "report_id": "report_1",
                    "transaction_id": "txn_1",
                    "amount_cad": 420.15,
                    "category": "Travel",
                    "policy_status": "approval_evidence_needed",
                    "risk_level": "low",
                    "created_at": "2026-05-02T00:00:00Z",
                }
            ],
        }
    )
    monkeypatch.setattr(reports_service, "get_supabase_client", lambda: client)

    response = reports_service.export_report_csv("report_1")

    assert response.file_name == "sarah-chen-2026-05-01-2026-05-31.csv"
    assert "Report Name,Sarah Chen" in response.csv
    assert "Total CAD,420.15" in response.csv
    assert "Missing preapproval count,1" in response.csv
    assert "AIR CANADA,Travel,420.15,submitted,missing,requested,approval_evidence_needed,low" in response.csv


def test_generate_report_prefers_recent_event_cluster_over_full_history(monkeypatch):
    client = FakeSupabaseClient(
        {
            "employees": [
                {
                    "id": "employee_1",
                    "department_id": "department_1",
                    "full_name": "Sarah Chen",
                    "email": "sarah@example.com",
                    "role": "Marketing Lead",
                }
            ],
            "departments": [{"id": "department_1", "name": "Marketing", "manager_name": "Maya Singh"}],
            "transactions": [
                transaction("txn_old", "2026-01-05", "SOFTWARE CO", 99, "Software"),
                transaction("txn_1", "2026-05-01", "AIR CANADA", 420.15, "Travel"),
                transaction("txn_2", "2026-05-03", "HOTEL", 300, "Lodging"),
                transaction("txn_3", "2026-05-05", "UBER", 40, "Ground Transportation"),
            ],
            "policy_checks": [],
            "risk_scores": [],
            "receipts": [],
            "preapprovals": [],
            "approval_requests": [],
            "expense_reports": [],
            "expense_report_items": [],
        }
    )
    monkeypatch.setattr(reports_service, "get_supabase_client", lambda: client)

    report = reports_service.generate_report(ReportGenerateRequest(request="Generate Sarah Chen report"))

    assert report.period_start == "2026-05-01"
    assert report.period_end == "2026-05-05"
    assert [item.transaction_id for item in report.line_items] == ["txn_1", "txn_2", "txn_3"]
    assert "recent 3-transaction" in (report.grouping_reason or "")


def test_generate_report_prefers_current_workflow_cluster_over_event_history(monkeypatch):
    client = FakeSupabaseClient(
        {
            "employees": [
                {
                    "id": "employee_1",
                    "department_id": "department_1",
                    "full_name": "Amelia Stone",
                    "email": "amelia@example.com",
                    "role": "Finance Lead",
                }
            ],
            "departments": [{"id": "department_1", "name": "Finance", "manager_name": "Maya Singh"}],
            "transactions": [
                transaction("txn_event_1", "2025-12-01", "AIR CANADA", 420.15, "Travel"),
                transaction("txn_event_2", "2025-12-03", "HOTEL", 300, "Lodging"),
                transaction("txn_event_3", "2025-12-05", "UBER", 40, "Ground Transportation"),
                transaction("txn_review_1", "2026-01-08", "ROSENBERG TR-LI", 413.53, "Cash Advance / ATM Withdrawal"),
                transaction("txn_review_2", "2026-01-08", "ROSENBERG TR-LI", 413.53, "Cash Advance / ATM Withdrawal"),
                transaction("txn_review_3", "2026-01-08", "ROSENBERG TR-LI", 109.47, "Cash Advance / ATM Withdrawal"),
                transaction("txn_review_4", "2026-01-08", "ROSENBERG TR-LI", 109.47, "Cash Advance / ATM Withdrawal"),
            ],
            "policy_checks": [
                {"id": "policy_1", "transaction_id": "txn_review_1", "status": "review_required", "created_at": "2026-01-08T00:00:00Z"}
            ],
            "risk_scores": [
                {"id": "risk_1", "transaction_id": "txn_review_1", "risk_level": "high", "risk_score": 76, "signals": [], "created_at": "2026-01-08T00:00:00Z"}
            ],
            "receipts": [],
            "preapprovals": [],
            "approval_requests": [
                {
                    "id": "approval_1",
                    "transaction_id": "txn_review_1",
                    "status": "denied",
                    "requested_amount_cad": 413.53,
                    "ai_recommendation": {"recommendation": "deny", "confidence": "high", "rationale": "Duplicate cash withdrawal."},
                    "created_at": "2026-01-08T01:00:00Z",
                }
            ],
            "review_queue_items": [
                {
                    "id": "review_1",
                    "transaction_id": "txn_review_1",
                    "queue_status": "resolved",
                    "review_priority": 80,
                    "review_level": "high",
                    "policy_status": "review_required",
                    "risk_level": "high",
                    "risk_score": 76,
                    "risk_signals": [],
                    "next_action": "Check whether this duplicates another card transaction before approving.",
                }
            ],
            "expense_reports": [],
            "expense_report_items": [],
        }
    )
    monkeypatch.setattr(reports_service, "get_supabase_client", lambda: client)

    report = reports_service.generate_report(ReportGenerateRequest(request="Generate Amelia Stone report", employee_name="Amelia Stone"))

    assert report.period_start == "2026-01-08"
    assert report.period_end == "2026-01-08"
    assert [item.transaction_id for item in report.line_items] == [
        "txn_review_1",
        "txn_review_2",
        "txn_review_3",
        "txn_review_4",
    ]
    assert report.line_items[0].approval_status == "denied"
    assert "current approval/review workflow cluster" in (report.grouping_reason or "")


def test_generate_report_can_use_ai_narrative_and_policy_citations(monkeypatch):
    class FakeNarrativeClient:
        def compose_report_narrative(self, facts):
            assert facts["report"]["item_count"] == 2
            return reports_service.ReportNarrative(
                title="Conference Expense Report",
                summary="Conference Expense Report covers 2 transactions from 2026-05-01 to 2026-05-03 totaling 720.15.",
            )

    client = FakeSupabaseClient(
        {
            "employees": [
                {
                    "id": "employee_1",
                    "department_id": "department_1",
                    "full_name": "Sarah Chen",
                    "email": "sarah@example.com",
                    "role": "Marketing Lead",
                }
            ],
            "departments": [{"id": "department_1", "name": "Marketing"}],
            "transactions": [
                transaction("txn_1", "2026-05-01", "AIR CANADA", 420.15, "Travel"),
                transaction("txn_2", "2026-05-03", "HOTEL", 300, "Lodging"),
            ],
            "policy_checks": [{"id": "policy_1", "transaction_id": "txn_2", "status": "approval_evidence_needed", "created_at": "2026-05-04T00:00:00Z"}],
            "risk_scores": [],
            "receipts": [],
            "preapprovals": [],
            "approval_requests": [],
            "violations": [
                {
                    "id": "violation_1",
                    "transaction_id": "txn_2",
                    "rule_code": "PREAPPROVAL_OVER_50",
                    "severity": "high",
                    "explanation": "Approval evidence is missing.",
                    "required_action": "Collect preapproval.",
                }
            ],
            "expense_reports": [],
            "expense_report_items": [],
        }
    )
    monkeypatch.setattr(reports_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(reports_service, "default_report_narrative_client", lambda: FakeNarrativeClient())
    monkeypatch.setattr(
        reports_service,
        "fetch_policy_citations_by_rule_code",
        lambda rule_codes: {
            "PREAPPROVAL_OVER_50": [
                CitedPolicyClause(
                    rule_code="PREAPPROVAL_OVER_50",
                    clause_id="clause_1",
                    title="Preapproval threshold",
                    text="All expenses over $50.00 must be pre-authorized by your manager.",
                    source="policy",
                )
            ]
        },
    )
    monkeypatch.setattr(
        reports_service,
        "retrieve_policy_chunks",
        lambda **_kwargs: type("Result", (), {"status": "ok", "chunks": []})(),
    )

    report = reports_service.generate_report(ReportGenerateRequest(request="Generate Sarah Chen report"))

    assert report.report_name == "Conference Expense Report"
    assert report.ai_summary == "Conference Expense Report covers 2 transactions from 2026-05-01 to 2026-05-03 totaling 720.15."
    assert report.policy_clauses[0].rule_code == "PREAPPROVAL_OVER_50"


def test_generate_report_refreshes_review_queue_only_for_selected_transactions(monkeypatch):
    client = FakeSupabaseClient(
        {
            "employees": [
                {
                    "id": "employee_1",
                    "department_id": "department_1",
                    "full_name": "Sarah Chen",
                    "email": "sarah@example.com",
                    "role": "Marketing Lead",
                }
            ],
            "departments": [{"id": "department_1", "name": "Marketing", "manager_name": "Maya Singh"}],
            "transactions": [
                transaction("txn_old", "2026-01-10", "SOFTWARE CO", 99, "Software"),
                transaction("txn_1", "2026-05-01", "AIR CANADA", 420.15, "Travel"),
                transaction("txn_2", "2026-05-03", "HOTEL", 300, "Lodging"),
            ],
            "policy_checks": [],
            "risk_scores": [],
            "receipts": [],
            "preapprovals": [],
            "approval_requests": [],
            "review_queue_items": [
                {
                    "id": "review_1",
                    "transaction_id": "txn_1",
                    "queue_status": "open",
                    "review_priority": 88,
                    "review_level": "high",
                    "created_at": "2026-05-03T00:00:00Z",
                },
                {
                    "id": "review_2",
                    "transaction_id": "txn_2",
                    "queue_status": "resolved",
                    "review_priority": 0,
                    "review_level": "low",
                    "created_at": "2026-05-04T00:00:00Z",
                },
                {
                    "id": "review_outside",
                    "transaction_id": "txn_old",
                    "queue_status": "open",
                    "review_priority": 91,
                    "review_level": "high",
                    "created_at": "2026-01-11T00:00:00Z",
                },
            ],
            "expense_reports": [],
            "expense_report_items": [],
        }
    )
    monkeypatch.setattr(reports_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(reports_service, "scan_policy_transactions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(reports_service, "scan_risk_scores", lambda *_args, **_kwargs: None)

    refreshed_transaction_ids = []

    def fake_refresh_review_queue_for_transaction_ids(transaction_ids, *, persist=True):
        refreshed_transaction_ids.append((list(transaction_ids), persist))
        return types.SimpleNamespace(
            generated=len(transaction_ids),
            persisted=len(transaction_ids),
            table_available=True,
            summary=None,
        )

    created_review_queue_item_ids = []

    def fake_create_approval_request(request):
        created_review_queue_item_ids.append(request.review_queue_item_id)
        return types.SimpleNamespace(id=f"approval_{len(created_review_queue_item_ids)}")

    monkeypatch.setattr(reports_service, "refresh_review_queue_for_transaction_ids", fake_refresh_review_queue_for_transaction_ids)
    monkeypatch.setattr(reports_service, "create_approval_request", fake_create_approval_request)

    report = reports_service.generate_report(
        ReportGenerateRequest(request="Generate Sarah Chen report", refresh_workflow=True)
    )

    assert report.period_start == "2026-05-01"
    assert report.period_end == "2026-05-03"
    assert refreshed_transaction_ids == [(["txn_1", "txn_2"], True)]
    assert created_review_queue_item_ids == ["review_1"]


def test_finalize_report_spec_drops_invalid_visuals_and_uses_safe_default():
    scope = reports_service.PlannedReportScope(
        scope_type="department",
        requested_label="Engineering",
        department_name="Engineering",
    )
    spec = reports_service.ReportSpec(
        title="Engineering Team Report",
        summary="Unsafe visual should be discarded.",
        visuals=[],
    )

    finalized = reports_service.finalize_report_spec(scope, "Engineering Team", spec)

    assert finalized.title == "Engineering Team Report"
    assert finalized.visuals[0].dimension == "employee"
    assert finalized.visuals[0].metric == "sum_amount_cad"


def transaction(transaction_id, transaction_date, merchant, amount, category, employee_id="employee_1", department_id="department_1"):
    return {
        "id": transaction_id,
        "employee_id": employee_id,
        "department_id": department_id,
        "transaction_date": transaction_date,
        "normalized_merchant_name": merchant,
        "merchant_name": merchant,
        "amount_cad": amount,
        "business_category": category,
        "normalized_category": category,
    }


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeSupabaseClient:
    def __init__(self, tables):
        self.tables = tables
        self.insert_counters = {"expense_reports": 0, "expense_report_items": 0}

    def table(self, table_name):
        return FakeQuery(self, table_name)


class FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.filters = []
        self.in_filter = None
        self.order_column = None
        self.order_desc = False
        self.limit_value = None
        self.range_value = None
        self.insert_payload = None

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def gte(self, column, value):
        self.filters.append((column, (">=", value)))
        return self

    def lte(self, column, value):
        self.filters.append((column, ("<=", value)))
        return self

    def in_(self, column, values):
        self.in_filter = (column, set(values))
        return self

    def order(self, column, desc=False):
        self.order_column = column
        self.order_desc = desc
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def range(self, start, end):
        self.range_value = (start, end)
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def execute(self):
        if self.insert_payload is not None:
            payloads = self.insert_payload if isinstance(self.insert_payload, list) else [self.insert_payload]
            inserted = []
            for payload in payloads:
                row = dict(payload)
                if "id" not in row:
                    self.client.insert_counters[self.table_name] = self.client.insert_counters.get(self.table_name, 0) + 1
                    prefix = "report" if self.table_name == "expense_reports" else "item"
                    row["id"] = f"{prefix}_{self.client.insert_counters[self.table_name]}"
                self.client.tables.setdefault(self.table_name, []).append(row)
                inserted.append(row)
            return FakeResponse(inserted)

        rows = [dict(row) for row in self.client.tables.get(self.table_name, [])]
        for column, expected in self.filters:
            if isinstance(expected, tuple):
                operator, value = expected
                if operator == ">=":
                    rows = [row for row in rows if str(row.get(column) or "") >= value]
                if operator == "<=":
                    rows = [row for row in rows if str(row.get(column) or "") <= value]
            else:
                rows = [row for row in rows if str(row.get(column) or "") == str(expected)]
        if self.in_filter:
            column, values = self.in_filter
            rows = [row for row in rows if str(row.get(column) or "") in values]
        if self.order_column:
            rows.sort(key=lambda row: str(row.get(self.order_column) or ""), reverse=self.order_desc)
        if self.range_value:
            start, end = self.range_value
            rows = rows[start : end + 1]
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return FakeResponse(rows)
