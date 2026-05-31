from app.schemas.insights import InsightPageContext, InsightPlan, InsightPlanRequest, InsightResultRow, InsightValidationResult
from app.schemas.review_queue import ReviewQueueItem, ReviewerBrief
from app.schemas.risk import RiskSignal
from app.config import Settings
from app.services import insights_service
from app.services import insight_artifact_service
from app.services.insight_artifact_service import load_stored_insight_result
from app.tools import spend_tools


def test_marketing_spend_by_category_plan_is_valid():
    response = insights_service.create_insight_plan(InsightPlanRequest(question="What did Marketing spend by category?"))

    assert response.validation.valid is True
    assert response.plan.tool == "spend.groupBy"
    assert response.plan.filters["department"] == "Marketing"
    assert response.plan.group_by == ["business_category"]


def test_compare_engineering_vs_sales_plan_is_valid():
    response = insights_service.create_insight_plan(InsightPlanRequest(question="Compare Engineering vs Sales spend."))

    assert response.validation.valid is True
    assert response.plan.tool == "spend.compare"
    assert response.plan.filters["department"] == ["Engineering", "Sales"]


def test_marketing_against_engineering_by_category_uses_compare_plan():
    response = insights_service.create_insight_plan(
        InsightPlanRequest(question="What did Marketing spend by category? How does it fare up against Engineering?")
    )

    assert response.validation.valid is True
    assert response.plan.tool == "spend.compare"
    assert response.plan.filters["department"] == ["Marketing", "Engineering"]
    assert response.plan.group_by == ["business_category"]
    assert response.plan.comparison_options["targets"] == ["Marketing", "Engineering"]


def test_top_merchants_plan_is_valid():
    response = insights_service.create_insight_plan(InsightPlanRequest(question="Show top merchants by spend."))

    assert response.validation.valid is True
    assert response.plan.tool == "spend.topMerchants"
    assert response.plan.limit == 10


def test_top_transactions_plan_is_valid():
    response = insights_service.create_insight_plan(
        InsightPlanRequest(question="Make a chart of the top 10 most expensive amounts on this table.")
    )

    assert response.validation.valid is True
    assert response.plan.tool == "spend.topTransactions"
    assert response.plan.mode == "chart"
    assert response.plan.limit == 10
    assert response.plan.visualization == "bar"


def test_last_quarter_chart_plan_uses_monthly_grouping():
    response = insights_service.create_insight_plan(
        InsightPlanRequest(question="How much did Marketing spend last quarter? Show me a chart")
    )

    assert response.validation.valid is True
    assert response.plan.tool == "spend.groupBy"
    assert response.plan.group_by == ["month"]
    assert response.plan.filters["department"] == "Marketing"
    assert response.plan.filters["date_start"] == "2026-01-01"
    assert response.plan.filters["date_end"] == "2026-03-31"
    assert response.plan.visualization == "line"


def test_high_risk_transactions_plan_is_valid():
    response = insights_service.create_insight_plan(InsightPlanRequest(question="Show high-risk transactions."))

    assert response.validation.valid is True
    assert response.plan.tool == "risk.latestSignals"
    assert response.plan.filters["risk_level"] == ["medium", "high", "critical"]


def test_policy_flags_by_department_plan_is_valid():
    response = insights_service.create_insight_plan(InsightPlanRequest(question="Show policy flags by department."))

    assert response.validation.valid is True
    assert response.plan.tool == "policy.latestFindings"
    assert response.plan.group_by == ["department"]


def test_review_queue_summary_plan_is_valid():
    response = insights_service.create_insight_plan(InsightPlanRequest(question="Summarize the current review queue."))

    assert response.validation.valid is True
    assert response.plan.tool == "review.currentQueue"
    assert response.plan.filters["queue_status"] == "open"
    assert response.plan.limit == 10


def test_review_queue_followup_keeps_context_and_explains_top_three():
    history = [
        type(
            "Message",
            (),
            {
                "role": "assistant",
                "metadata": {
                    "plan": {
                        "intent": "review_queue_summary",
                        "mode": "table",
                        "tool": "review.currentQueue",
                        "filters": {"queue_status": "open"},
                        "group_by": [],
                        "metrics": ["sum_amount_cad", "transaction_count"],
                        "sort": [{"field": "review_priority", "direction": "desc"}],
                        "limit": 10,
                        "visualization": "table",
                        "comparison_options": {},
                        "report_options": {},
                    }
                },
            },
        )()
    ]

    response = insights_service.create_insight_plan(
        InsightPlanRequest(question="Can you explain why the top three flagged are critical?"),
        session_messages=history,
    )

    assert response.validation.valid is True
    assert response.plan.tool == "review.currentQueue"
    assert response.plan.intent == "review_queue_explanation"
    assert response.plan.filters["queue_status"] == "open"
    assert response.plan.filters["review_level"] == "critical"
    assert response.plan.limit == 3


def test_policy_clause_lookup_plan_is_valid():
    response = insights_service.create_insight_plan(InsightPlanRequest(question="What does policy say about receipts?"))

    assert response.validation.valid is True
    assert response.plan.tool == "policy.retrieveClauses"


def test_global_reports_summary_plan_is_valid():
    response = insights_service.create_insight_plan(InsightPlanRequest(question="What reports have been generated?"))

    assert response.validation.valid is True
    assert response.plan.tool == "context.globalSummary"
    assert response.plan.context_options["summary_keys"] == ["reports"]


def test_validator_rejects_raw_sql_and_unknown_fields():
    plan = InsightPlan(
        intent="unsafe",
        tool="spend.summary",
        filters={"raw_sql": "select * from transactions"},
        group_by=["unknown_dimension"],
        metrics=["made_up_metric"],
        limit=501,
    )

    result = insights_service.validate_plan(plan)

    assert result.valid is False
    assert any("raw SQL" in error for error in result.errors)
    assert any("Unsupported metrics" in error for error in result.errors)
    assert any("Unsupported dimensions" in error for error in result.errors)
    assert any("Unsupported filters" in error for error in result.errors)
    assert any("limit" in error for error in result.errors)


def test_query_insights_returns_category_comparison_rows_and_persists_session(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction("txn_1", "employee_1", "department_1", "Fuel", 200, "PETRO"),
                transaction("txn_2", "employee_1", "department_1", "Travel", 80, "AIR CANADA"),
                transaction("txn_3", "employee_2", "department_2", "Fuel", 120, "SHELL"),
                transaction("txn_4", "employee_2", "department_2", "Travel", 300, "DELTA"),
            ],
            "employees": [
                {"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"},
                {"id": "employee_2", "full_name": "Ava Cole", "department_id": "department_2"},
            ],
            "departments": [
                {"id": "department_1", "name": "Marketing"},
                {"id": "department_2", "name": "Engineering"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "What did Marketing spend by category? How does it fare up against Engineering?",
                "mode": None,
                "session_id": None,
            },
        )()
    )

    assert response.session_id is not None
    assert response.plan.tool == "spend.compare"
    assert response.rows[0].label == "Travel"
    assert response.rows[0].values["marketing_sum_amount_cad"] == 80
    assert response.rows[0].values["engineering_sum_amount_cad"] == 300
    assert response.rows[0].values["total_sum_amount_cad"] == 380
    assert "Marketing" in response.summary
    assert "Engineering" in response.summary
    assert "CAD 280.00" in response.summary
    assert "CAD 420.00" in response.summary
    assert len(client.tables["chat_sessions"]) == 1
    assert len(client.tables["chat_messages"]) == 2
    assistant_message = client.tables["chat_messages"][1]
    assert assistant_message["metadata"]["session_id"] == response.session_id
    assert assistant_message["metadata"]["validation"]["valid"] is True


def test_followup_question_reuses_previous_session_filters(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction("txn_1", "employee_1", "department_1", "Fuel", 200, "PETRO"),
                transaction("txn_2", "employee_1", "department_1", "Travel", 80, "AIR CANADA"),
                transaction("txn_3", "employee_2", "department_2", "Fuel", 120, "SHELL"),
            ],
            "employees": [
                {"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"},
                {"id": "employee_2", "full_name": "Ava Cole", "department_id": "department_2"},
            ],
            "departments": [
                {"id": "department_1", "name": "Marketing"},
                {"id": "department_2", "name": "Engineering"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    first = insights_service.query_insights(
        type("Request", (), {"question": "What did Marketing spend by category?", "mode": None, "session_id": None})()
    )
    second = insights_service.query_insights(
        type("Request", (), {"question": "Now only Marketing merchants", "mode": None, "session_id": first.session_id})()
    )

    assert second.session_id == first.session_id
    assert second.plan.filters["department"] == "Marketing"
    assert second.plan.tool == "spend.topMerchants"
    assert second.plan.intent == "top_merchants"
    assert second.plan.mode == "table"


def test_department_followup_reframes_top_transactions_into_department_spend(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction("txn_1", "employee_1", "department_1", "Office", 1250, "AMAZON"),
                transaction("txn_2", "employee_1", "department_1", "Travel", 980, "AIR CANADA"),
                transaction("txn_3", "employee_2", "department_2", "Software", 640, "ATLASSIAN"),
                transaction("txn_4", "employee_2", "department_2", "Travel", 560, "UBER"),
            ],
            "employees": [
                {"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"},
                {"id": "employee_2", "full_name": "Ava Cole", "department_id": "department_2"},
            ],
            "departments": [
                {"id": "department_1", "name": "Marketing"},
                {"id": "department_2", "name": "Engineering"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    first = insights_service.query_insights(
        type("Request", (), {"question": "Can you make a chart showing top 5 biggest amounts?", "mode": None, "session_id": None})()
    )
    second = insights_service.query_insights(
        type("Request", (), {"question": "What about Engineering's spending?", "mode": None, "session_id": first.session_id})()
    )

    assert second.plan.tool == "spend.summary"
    assert second.plan.intent == "department_spend_summary"
    assert second.plan.filters["department"] == "Engineering"
    assert second.summary.startswith("Engineering spend totaled CAD")


def test_department_trend_summary_mentions_chart_and_period(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                {
                    **transaction("txn_1", "employee_2", "department_2", "Software", 100, "ATLASSIAN"),
                    "transaction_date": "2026-01-05",
                },
                {
                    **transaction("txn_2", "employee_2", "department_2", "Software", 150, "ATLASSIAN"),
                    "transaction_date": "2026-02-10",
                },
                {
                    **transaction("txn_3", "employee_2", "department_2", "Travel", 90, "UBER"),
                    "transaction_date": "2026-03-12",
                },
            ],
            "employees": [
                {"id": "employee_2", "full_name": "Ava Cole", "department_id": "department_2"},
            ],
            "departments": [
                {"id": "department_2", "name": "Engineering"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "Show me a graph of Engineering department expenses last quarter",
                "mode": None,
                "session_id": None,
            },
        )()
    )

    assert response.plan.tool == "spend.groupBy"
    assert response.plan.filters["department"] == "Engineering"
    assert response.plan.visualization == "line"
    assert response.summary.startswith("I plotted Engineering spend by month")
    assert "January 2026" in response.summary
    assert "March 2026" in response.summary


def test_review_queue_query_and_followup_feel_conversational(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [],
            "employees": [],
            "departments": [],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    items = [
        ReviewQueueItem(
            transaction_id="txn_critical_1",
            employee="Alex Rivera",
            department="Marketing",
            merchant="AIR CANADA",
            amount_cad=1480.25,
            category="Travel",
            queue_status="open",
            review_priority=98,
            review_level="critical",
            policy_status="policy_violation",
            policy_flags=[
                {"rule_code": "PREAPPROVAL_OVER_50", "explanation": "approval evidence is missing for a high-value travel charge"}
            ],
            risk_level="critical",
            risk_score=92,
            risk_signals=[RiskSignal(type="split_transaction_pattern", severity="high", message="charges appear split around the threshold", evidence={})],
            next_action="Escalate to manager approval.",
            reviewer_brief=ReviewerBrief(summary="Missing preapproval and suspicious threshold-splitting pattern.", recommended_next_action="Escalate to manager approval."),
        ),
        ReviewQueueItem(
            transaction_id="txn_critical_2",
            employee="Jordan Lee",
            department="Sales",
            merchant="STAPLES",
            amount_cad=860.0,
            category="Office",
            queue_status="open",
            review_priority=93,
            review_level="critical",
            policy_status="review_required",
            policy_flags=[{"rule_code": "RECEIPT_REQUIRED", "explanation": "receipt evidence is missing"}],
            risk_level="high",
            risk_score=80,
            risk_signals=[RiskSignal(type="duplicate_charge", severity="high", message="duplicate charge pattern detected", evidence={})],
            next_action="Request receipt and duplicate-charge confirmation.",
            reviewer_brief=ReviewerBrief(summary="Missing receipt plus duplicate-charge pattern requires reviewer confirmation.", recommended_next_action="Request receipt and duplicate-charge confirmation."),
        ),
        ReviewQueueItem(
            transaction_id="txn_critical_3",
            employee="Taylor Chen",
            department="Engineering",
            merchant="UBER",
            amount_cad=420.0,
            category="Travel",
            queue_status="open",
            review_priority=89,
            review_level="critical",
            policy_status="context_needed",
            policy_flags=[{"rule_code": "ENTERTAINMENT_CONTEXT_REQUIRED", "explanation": "business context is incomplete"}],
            risk_level="medium",
            risk_score=67,
            risk_signals=[RiskSignal(type="ml_isolation_forest_outlier", severity="medium", message="transaction looks unusual for the employee history", evidence={})],
            next_action="Gather business context before reimbursement.",
            reviewer_brief=ReviewerBrief(summary="Incomplete business context plus anomalous activity keeps this in critical review.", recommended_next_action="Gather business context before reimbursement."),
        ),
        ReviewQueueItem(
            transaction_id="txn_high_1",
            employee="Morgan Blake",
            department="Finance",
            merchant="DELTA",
            amount_cad=300.0,
            category="Travel",
            queue_status="open",
            review_priority=72,
            review_level="high",
            policy_status="approval_evidence_needed",
            policy_flags=[],
            risk_level="low",
            risk_score=21,
            risk_signals=[],
            next_action="Attach approval evidence.",
        ),
    ]

    def fake_list_review_queue(limit=100, offset=0, queue_status="open", review_level=None, policy_status=None):
        filtered = items
        if queue_status:
            filtered = [item for item in filtered if item.queue_status == queue_status]
        if review_level:
            filtered = [item for item in filtered if item.review_level == review_level]
        if policy_status:
            filtered = [item for item in filtered if item.policy_status == policy_status]
        return filtered[offset : offset + limit]

    monkeypatch.setattr(spend_tools, "list_review_queue", fake_list_review_queue)

    first = insights_service.query_insights(
        type("Request", (), {"question": "Summarize the current review queue.", "mode": None, "session_id": None, "page_context": None})()
    )
    second = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "Can you explain why the top three flagged are critical?",
                "mode": None,
                "session_id": first.session_id,
                "page_context": None,
            },
        )()
    )

    assert first.plan.tool == "review.currentQueue"
    assert "review queue" in first.summary
    assert "4" in first.summary
    assert "open" in first.summary
    assert second.plan.tool == "review.currentQueue"
    assert second.plan.filters["review_level"] == "critical"
    assert second.plan.limit == 3
    assert "AIR CANADA" in second.summary
    assert "critical because" in second.summary


def test_page_explanation_question_prefers_review_context(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [],
            "employees": [],
            "departments": [],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "default_insight_response_client", lambda: None)

    items = [
        ReviewQueueItem(
            transaction_id="txn_critical_1",
            employee="Sarah Chen",
            department="Marketing",
            merchant="ROSENBERG TR-LI",
            amount_cad=413.53,
            category="Travel",
            queue_status="open",
            review_priority=88,
            review_level="critical",
            policy_status="review_required",
            policy_flags=[{"rule_code": "RECEIPT_REQUIRED", "explanation": "receipt evidence is unavailable in the dataset"}],
            risk_level="critical",
            risk_score=91,
            risk_signals=[RiskSignal(type="cash_like_activity", severity="critical", message="cash-like indicators are harder to substantiate", evidence={})],
            next_action="Review business purpose and supporting evidence.",
            reviewer_brief=ReviewerBrief(
                summary="This item needs reviewer attention because it combines missing evidence with critical risk signals.",
                recommended_next_action="Review business purpose and supporting evidence.",
            ),
        )
    ]

    monkeypatch.setattr(spend_tools, "list_review_queue", lambda **_kwargs: items)

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "What am I looking at here",
                "mode": None,
                "session_id": None,
                "page_context": InsightPageContext(
                    page="Review",
                    route="compliance",
                    payload={
                        "summary": "Reviewing 1 open queue item with 1 high or critical case.",
                        "filters": {"review_level": "critical", "queue_status": "open"},
                        "metrics": {
                            "total_scanned": 4235,
                            "open_queue_items": 1,
                            "review_required": 44,
                            "high_or_critical": 1,
                        },
                        "details": {
                            "quick_summary": "The screen combines policy findings, risk signals, and reviewer next steps.",
                            "top_items": [
                                {
                                    "merchant": "ROSENBERG TR-LI",
                                    "amount_cad": 413.53,
                                    "policy_status": "review_required",
                                }
                            ],
                        },
                    },
                ),
            },
        )()
    )

    assert response.plan.tool == "review.currentQueue"
    assert response.plan.filters["queue_status"] == "open"
    assert response.plan.filters["review_level"] == "critical"
    assert response.summary.startswith("You're on the Review page.")
    assert "policy findings, risk signals, and reviewer next steps" in response.summary
    assert "ROSENBERG TR-LI at CAD 413.53" in response.summary


def test_query_insights_applies_page_context_filters(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction("txn_1", "employee_1", "department_1", "Travel", 200, "AIR CANADA"),
                transaction("txn_2", "employee_2", "department_2", "Travel", 120, "DELTA"),
            ],
            "employees": [
                {"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"},
                {"id": "employee_2", "full_name": "Ava Cole", "department_id": "department_2"},
            ],
            "departments": [
                {"id": "department_1", "name": "Marketing"},
                {"id": "department_2", "name": "Engineering"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "Show top merchants",
                "mode": None,
                "session_id": None,
                "page_context": InsightPageContext(
                    page="reports",
                    route="/reports/report_1",
                    payload={"filters": {"department_name": "Marketing", "period_start": "2026-05-01", "period_end": "2026-05-31"}},
                ),
            },
        )()
    )

    assert response.plan.tool == "spend.topMerchants"
    assert response.plan.filters["department"] == "Marketing"
    assert response.plan.filters["date_start"] == "2026-05-01"
    assert response.plan.filters["date_end"] == "2026-05-31"
    assert response.rows[0].label == "AIR CANADA"
    assert response.metadata["page_context"]["page"] == "reports"


def test_query_insights_uses_visible_transaction_ids_for_top_transactions(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction("txn_1", "employee_1", "department_1", "Travel", 200, "AIR CANADA"),
                transaction("txn_2", "employee_1", "department_1", "Office", 80, "STAPLES"),
                transaction("txn_3", "employee_2", "department_2", "Travel", 450, "DELTA"),
                transaction("txn_4", "employee_2", "department_2", "Meals", 125, "UBER EATS"),
            ],
            "employees": [
                {"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"},
                {"id": "employee_2", "full_name": "Ava Cole", "department_id": "department_2"},
            ],
            "departments": [
                {"id": "department_1", "name": "Marketing"},
                {"id": "department_2", "name": "Engineering"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "Make a chart of the top 2 most expensive amounts on this table.",
                "mode": None,
                "session_id": None,
                "page_context": InsightPageContext(
                    page="Transactions",
                    route="transactions",
                    payload={"filters": {"visible_transaction_ids": ["txn_1", "txn_2", "txn_4"]}},
                ),
            },
        )()
    )

    assert response.plan.tool == "spend.topTransactions"
    assert response.plan.filters["transaction_ids"] == ["txn_1", "txn_2", "txn_4"]
    assert [row.values["transaction_id"] for row in response.rows] == ["txn_1", "txn_4"]
    assert response.rows[0].values["amount_cad"] == 200
    assert "Top transaction is AIR CANADA" in response.summary


def test_talk_to_data_page_uses_grounded_fallback_summary_even_with_page_context(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction("txn_1", "employee_1", "department_1", "Travel", 200, "AIR CANADA"),
            ],
            "employees": [
                {"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"},
            ],
            "departments": [
                {"id": "department_1", "name": "Marketing"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    class FakeResponseClient:
        def compose_answer(self, _facts):
            return "This should not be used for Talk to Data."

    monkeypatch.setattr(insights_service, "default_insight_response_client", lambda: FakeResponseClient())

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "What did Marketing spend?",
                "mode": None,
                "session_id": None,
                "page_context": InsightPageContext(page="Talk to Data", route="talkToData", payload={}),
            },
        )()
    )

    assert response.summary == "All matching spend: CAD 200.00 across 1 transaction(s)."


def test_query_insights_uses_ai_response_composer_when_available(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction("txn_1", "employee_1", "department_1", "Travel", 200, "AIR CANADA"),
            ],
            "employees": [
                {"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"},
            ],
            "departments": [
                {"id": "department_1", "name": "Marketing"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    captured: dict[str, object] = {}

    class FakeResponseClient:
        def compose_answer(self, facts):
            captured.update(facts)
            return "You're looking at Marketing travel spend on the current page."

    monkeypatch.setattr(insights_service, "default_insight_response_client", lambda: FakeResponseClient())

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "What am I looking at here?",
                "mode": None,
                "session_id": None,
                "page_context": InsightPageContext(page="Reports", route="reports", payload={"summary": "Marketing report view"}),
            },
        )()
    )

    assert response.summary == "You're looking at Marketing travel spend on the current page."
    assert captured["question"] == "What am I looking at here?"
    assert captured["fallback_summary"] == "Pulled 1 app-wide summary view(s): Reports."


def test_query_insights_answers_from_global_context_summary(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [],
            "employees": [],
            "departments": [],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(
        insights_service.ask_context_service,
        "build_ask_context_envelope",
        lambda **_kwargs: insights_service.AskContextEnvelope(
            page_context=InsightPageContext(page="Overview", route="dashboard", payload={"summary": "Overview page"}),
            global_summaries={
                "dashboard": {
                    "normalized_transaction_count": 4235,
                    "raw_transaction_count": 4235,
                    "employee_count": 16,
                    "department_count": 8,
                },
                "review": {"queue": {"open": 44, "high_or_critical": 12}},
                "approvals": {"active": 6, "decided": 9, "total": 15},
                "reports": {"report_count": 4, "top_reports": [{"label": "Marketing May 2026"}]},
                "policy_setup": {"active_rules": 12, "draft_rules": 3, "latest_document": {"title": "Expense Policy 2026"}},
            },
            focus_entities=[],
            visible_entities=[],
            artifacts=[],
            hydrated_entities={},
            recent_results=[{"summary": "Last answer summarized policy findings."}],
            recent_artifacts=[],
            context_scope=["page_context", "global_summaries", "session_memory"],
        ),
    )

    class FakeResponseClient:
        def compose_answer(self, _facts):
            return "Across the app, there are 4 saved reports, 6 active approvals, and 44 open review items."

    monkeypatch.setattr(insights_service, "default_insight_response_client", lambda: FakeResponseClient())

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {
                "question": "Give me an overview of the app right now.",
                "mode": None,
                "session_id": None,
                "page_context": InsightPageContext(page="Overview", route="dashboard", payload={"summary": "Overview page"}),
            },
        )()
    )

    assert response.plan.tool == "context.globalSummary"
    assert response.summary.startswith("Across the app")
    assert "global_summary" in response.metadata["grounding_sources"]
    assert "session_memory" in response.metadata["grounding_sources"]
    assert response.metadata["artifact_capabilities"] == ["brief", "csv", "diagram"]
    assert response.metadata["context_scope"] == ["page_context", "global_summaries", "session_memory"]


def test_query_insights_executes_validated_sql_plan(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [],
            "employees": [],
            "departments": [],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(
        insights_service,
        "create_insight_plan",
        lambda request, session_messages=None, page_context=None, ask_context=None: type(
            "PlanResponse",
            (),
            {
                "question": request.question,
                "plan": InsightPlan(
                    intent="validated_sql_department_spend",
                    mode="chart",
                    tool="spend.sqlQuery",
                    limit=10,
                    visualization="bar",
                    sql_statement=(
                        "select department as label, sum(amount_cad) as sum_amount_cad "
                        "from review_queue_items group by department order by sum_amount_cad desc"
                    ),
                ),
                "critic": InsightValidationResult(valid=True),
                "validation": InsightValidationResult(valid=True),
                "planner_source": "anthropic_structured",
            },
        )(),
    )

    monkeypatch.setattr(
        insights_service.sql_query_service,
        "validate_and_prepare_sql",
        lambda **_kwargs: (
            "select * from (select department as label, 10 as sum_amount_cad) as insight_query limit 10",
            {
                "generated_sql": "select department as label, 10 as sum_amount_cad",
                "executed_sql": "select * from (select department as label, 10 as sum_amount_cad) as insight_query limit 10",
                "sql_validation": {"approved": True, "reason": "read-only"},
            },
        ),
    )
    monkeypatch.setattr(
        insights_service.sql_query_service,
        "execute_read_only_sql",
        lambda _sql, _limit: (
            [
                InsightResultRow(label="Marketing", values={"sum_amount_cad": 282819.61}),
                InsightResultRow(label="Engineering", values={"sum_amount_cad": 406114.26}),
            ],
            {"record_count": 2, "returned_count": 2, "sql_columns": ["label", "sum_amount_cad"], "sql_limit": 10},
        ),
    )

    response = insights_service.query_insights(
        type("Request", (), {"question": "Compare department spend and show me a chart", "mode": None, "session_id": None, "page_context": None})()
    )

    assert response.plan.tool == "spend.sqlQuery"
    assert response.rows[0].label == "Marketing"
    assert response.metadata["generated_sql"] == "select department as label, 10 as sum_amount_cad"
    assert response.metadata["sql_validation"]["approved"] is True
    assert "Returned 2 row(s)" in response.summary


def test_query_insights_reuses_saved_session_context(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction("txn_1", "employee_1", "department_1", "Travel", 200, "AIR CANADA"),
                transaction("txn_2", "employee_2", "department_2", "Travel", 120, "DELTA"),
            ],
            "employees": [
                {"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"},
                {"id": "employee_2", "full_name": "Ava Cole", "department_id": "department_2"},
            ],
            "departments": [
                {"id": "department_1", "name": "Marketing"},
                {"id": "department_2", "name": "Engineering"},
            ],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)

    session = insights_service.create_insight_session(
        type(
            "SessionRequest",
            (),
            {
                "title": None,
                "initial_question": None,
                "page_context": InsightPageContext(page="reports", payload={"department_name": "Marketing"}),
            },
        )()
    )
    response = insights_service.query_insights(
        type("Request", (), {"question": "Show top merchants", "mode": None, "session_id": session.id, "page_context": None})()
    )

    assert response.plan.filters["department"] == "Marketing"
    session_messages = insights_service.get_insight_session(session.id).messages
    assert all(message.metadata.get("kind") != "session_context" for message in session_messages)


def test_stored_insight_result_keeps_full_rows_for_artifact_downloads(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [
                transaction(f"txn_{index}", "employee_1", "department_1", f"Category {index:02d}", 100 + index, f"MERCHANT {index:02d}")
                for index in range(13)
            ],
            "employees": [{"id": "employee_1", "full_name": "Sarah Chen", "department_id": "department_1"}],
            "departments": [{"id": "department_1", "name": "Marketing"}],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insight_artifact_service, "get_supabase_client", lambda: client)

    response = insights_service.query_insights(
        type(
            "Request",
            (),
            {"question": "What did Marketing spend by category?", "mode": None, "session_id": None, "page_context": None},
        )()
    )
    stored = load_stored_insight_result(response.session_id or "")

    assert len(response.rows) == 13
    assert len(stored.rows) == 13
    assert len(client.tables["chat_messages"][1]["metadata"]["rows"]) == 12
    assert len(client.tables["chat_messages"][1]["metadata"]["artifact_rows"]) == 13


def test_policy_clause_lookup_returns_citations(monkeypatch):
    client = FakeSupabaseClient(
        {
            "transactions": [],
            "employees": [],
            "departments": [],
            "policy_checks": [],
            "risk_scores": [],
            "chat_sessions": [],
            "chat_messages": [],
        }
    )
    monkeypatch.setattr(spend_tools, "get_supabase_client", lambda: client)
    monkeypatch.setattr(insights_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(
        spend_tools,
        "retrieve_policy_chunks",
        lambda query: type(
            "Retrieval",
            (),
            {
                "chunks": [
                    type(
                        "Chunk",
                        (),
                        {
                            "id": "chunk_1",
                            "rule_code": "RECEIPT_REQUIRED",
                            "content": "Receipts are required before reimbursement can be completed.",
                            "similarity": 0.92,
                            "document_id": "doc_1",
                            "citation": {"section_label": "Receipts", "document_id": "doc_1"},
                        },
                    )()
                ]
            },
        )(),
    )

    response = insights_service.query_insights(
        type("Request", (), {"question": "What does policy say about receipts?", "mode": None, "session_id": None})()
    )

    assert response.plan.tool == "policy.retrieveClauses"
    assert response.citations[0].rule_code == "RECEIPT_REQUIRED"
    assert response.rows[0].values["text"].startswith("Receipts are required")


def test_ai_planner_uses_anthropic_for_followup_questions(monkeypatch):
    monkeypatch.setattr(insights_service, "maybe_apply_followup_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        insights_service.AnthropicInsightPlannerClient,
        "create_plan",
        lambda self, **_kwargs: InsightPlan(
            intent="top_merchants",
            mode="table",
            tool="spend.topMerchants",
            filters={"department": "Marketing"},
            metrics=["sum_amount_cad", "transaction_count"],
            group_by=["merchant"],
            sort=[{"field": "sum_amount_cad", "direction": "desc"}],
            limit=25,
            visualization="table",
        ),
    )

    history = [
        type(
            "Message",
            (),
            {
                "role": "assistant",
                "metadata": {
                    "plan": {
                        "intent": "marketing_spend_by_category",
                        "mode": "chart",
                        "tool": "spend.groupBy",
                        "filters": {"department": "Marketing"},
                        "group_by": ["business_category"],
                        "metrics": ["sum_amount_cad"],
                        "sort": [],
                        "limit": 100,
                        "visualization": "bar",
                        "comparison_options": {},
                        "report_options": {},
                    }
                },
            },
        )()
    ]

    response = insights_service.create_insight_plan(
        InsightPlanRequest(question="What about merchants?", mode=None),
        session_messages=history,
    )

    assert response.planner_source == "anthropic_structured"
    assert response.plan.tool == "spend.topMerchants"
    assert response.plan.mode == "table"


def test_anthropic_insight_planner_uses_talk_to_data_model_override(monkeypatch):
    captured: dict[str, str] = {}

    class FakeAnthropicClient:
        def __init__(self, *, api_key: str):
            captured["api_key"] = api_key

    class FakeSettings:
        anthropic_api_key = "test-key"
        resolved_anthropic_insights_model = "claude-sonnet-4-6"

    monkeypatch.setattr(insights_service, "Anthropic", FakeAnthropicClient)
    monkeypatch.setattr(insights_service, "get_settings", lambda: FakeSettings())

    client = insights_service.AnthropicInsightPlannerClient()

    assert captured["api_key"] == "test-key"
    assert client._model == "claude-sonnet-4-6"


def test_settings_resolve_anthropic_model2_for_talk_to_data():
    settings = Settings(
        ANTHROPIC_API_KEY="test-key",
        ANTHROPIC_MODEL="claude-haiku-4-5",
        ANTHROPIC_MODEL2="claude-sonnet-4-6",
    )

    assert settings.resolved_anthropic_insights_model == "claude-sonnet-4-6"


def transaction(transaction_id, employee_id, department_id, category, amount_cad, merchant):
    return {
        "id": transaction_id,
        "employee_id": employee_id,
        "department_id": department_id,
        "transaction_date": "2026-05-01",
        "posting_date": "2026-05-02",
        "normalized_merchant_name": merchant,
        "merchant_name": merchant,
        "amount_cad": amount_cad,
        "business_category": category,
        "normalized_category": category,
        "created_at": "2026-05-01T00:00:00Z",
    }


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeSupabaseClient:
    def __init__(self, tables):
        self.tables = {name: [dict(row) for row in rows] for name, rows in tables.items()}
        self.next_ids = {"chat_sessions": 1, "chat_messages": 1}

    def table(self, table_name):
        self.tables.setdefault(table_name, [])
        return FakeQuery(self, table_name)


class FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self._order_column = None
        self._order_desc = False
        self._range_value = None
        self._limit_value = None
        self._filters = []
        self._pending_insert = None

    @property
    def rows(self):
        return self.client.tables[self.table_name]

    def select(self, _columns):
        return self

    def order(self, column, desc=False):
        self._order_column = column
        self._order_desc = desc
        return self

    def range(self, start, end):
        self._range_value = (start, end)
        return self

    def limit(self, value):
        self._limit_value = value
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def insert(self, payload):
        self._pending_insert = payload
        return self

    def execute(self):
        if self._pending_insert is not None:
            inserted = self._insert_rows(self._pending_insert)
            return FakeResponse(inserted)

        rows = [dict(row) for row in self.rows]
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        if self._order_column:
            rows.sort(key=lambda row: str(row.get(self._order_column) or ""), reverse=self._order_desc)
        if self._range_value:
            start, end = self._range_value
            rows = rows[start : end + 1]
        if self._limit_value is not None:
            rows = rows[: self._limit_value]
        return FakeResponse(rows)

    def _insert_rows(self, payload):
        rows = payload if isinstance(payload, list) else [payload]
        inserted = []
        for row in rows:
            next_row = dict(row)
            if self.table_name in self.client.next_ids and "id" not in next_row:
                next_row["id"] = f"{self.table_name}_{self.client.next_ids[self.table_name]}"
                self.client.next_ids[self.table_name] += 1
            if self.table_name == "chat_sessions":
                next_row.setdefault("created_at", "2026-05-31T00:00:00Z")
                next_row.setdefault("updated_at", "2026-05-31T00:00:00Z")
            if self.table_name == "chat_messages":
                next_row.setdefault("created_at", "2026-05-31T00:00:00Z")
                next_row.setdefault("metadata", {})
            self.rows.append(next_row)
            inserted.append(dict(next_row))
        return inserted
