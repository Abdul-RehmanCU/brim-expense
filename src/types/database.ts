export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

type TableDef<Row, Insert = Partial<Row>, Update = Partial<Row>> = {
  Row: Row
  Insert: Insert
  Update: Update
  Relationships: []
}

export type Database = {
  public: {
    Tables: {
      departments: TableDef<{
        id: string
        name: string
        manager_name: string
        monthly_budget_cad: number
        quarterly_budget_cad: number
        synthetic: boolean
        created_at: string
        updated_at: string
      }>
      employees: TableDef<{
        id: string
        department_id: string
        manager_employee_id: string | null
        full_name: string
        email: string
        role: string
        synthetic: boolean
        created_at: string
        updated_at: string
      }>
      raw_transactions: TableDef<{
        id: string
        source_file_name: string | null
        source_row_number: number
        source_fingerprint: string
        raw_payload: Json
        import_batch_id: string | null
        synthetic_context_assigned: boolean
        created_at: string
      }>
      transactions: TableDef<{
        id: string
        raw_transaction_id: string | null
        employee_id: string | null
        department_id: string | null
        transaction_code: string | null
        transaction_type: string | null
        transaction_eligibility: string | null
        description: string | null
        source_category: string | null
        network_category_code: string | null
        business_category: string | null
        policy_category: string | null
        category_source: string | null
        normalized_category: string
        normalized_merchant_family: string | null
        category_confidence: number
        mcc_description: string | null
        amount_bucket: string | null
        posting_delay_days: number | null
        is_account_activity: boolean
        is_credit_or_refund: boolean
        is_foreign_transaction: boolean
        posting_date: string | null
        transaction_date: string | null
        merchant_name: string | null
        normalized_merchant_name: string | null
        amount_original: number
        amount_cad: number
        debit_credit: 'debit' | 'credit'
        merchant_category_code: string | null
        merchant_city: string | null
        merchant_country: string | null
        merchant_postal_code: string | null
        merchant_region: string | null
        conversion_rate: number | null
        synthetic_assignment: boolean
        business_purpose: string | null
        guest_names: string[] | null
        created_at: string
        updated_at: string
      }>
      receipts: TableDef<{
        id: string
        transaction_id: string
        storage_path: string | null
        file_name: string | null
        receipt_date: string | null
        submitted_at: string | null
        status: 'unavailable' | 'missing' | 'submitted' | 'approved' | 'rejected'
        synthetic: boolean
        created_at: string
        updated_at: string
      }>
      preapprovals: TableDef<{
        id: string
        employee_id: string
        transaction_id: string | null
        department_id: string | null
        requested_amount_cad: number
        status: 'not_required' | 'missing' | 'requested' | 'approved' | 'denied'
        requested_at: string | null
        approved_at: string | null
        approver_employee_id: string | null
        approver_name: string | null
        business_purpose: string | null
        synthetic: boolean
        created_at: string
        updated_at: string
      }>
      policy_rules: TableDef<{
        id: string
        rule_code: string
        title: string
        name: string | null
        description: string
        severity: 'low' | 'medium' | 'high' | 'critical'
        deterministic: boolean
        active: boolean
        enabled: boolean
        status: 'active' | 'draft' | 'disabled'
        source_type: string
        source_text: string | null
        rule_json: Json
        conditions_json: Json
        outcome_json: Json
        scope_json: Json
        applies_to_json: Json
        context_requirements_json: Json
        requires_json: Json
        policy_document_id: string | null
        policy_extraction_run_id: string | null
        extraction_confidence: number | null
        needs_human_review: boolean
        validation_errors: Json
        effective_date: string | null
        synthetic: boolean
        created_at: string
        updated_at: string
      }>
      policy_checks: TableDef<{
        id: string
        transaction_id: string
        status:
          | 'compliant'
          | 'excluded_non_expense'
          | 'review_required'
          | 'context_needed'
          | 'approval_evidence_needed'
          | 'policy_violation'
        max_severity: 'low' | 'medium' | 'high' | 'critical'
        severity_score: number
        scan_version: string | null
        missing_information: string[]
        recommended_next_action: string
        checked_at: string
        engine_version: string
        created_at: string
      }>
      violations: TableDef<{
        id: string
        policy_check_id: string
        transaction_id: string
        policy_rule_id: string | null
        rule_code: string
        severity: 'low' | 'medium' | 'high' | 'critical'
        explanation: string
        required_action: string
        status: string
        created_at: string
      }>
      risk_scores: TableDef<{
        id: string
        transaction_id: string
        risk_score: number
        risk_level: string
        signals: Json
        scored_at: string
        engine_version: string
        created_at: string
      }>
      approval_requests: TableDef<{
        id: string
        transaction_id: string
        employee_id: string
        department_id: string
        status: 'draft' | 'requested' | 'approved' | 'denied' | 'cancelled'
        requested_amount_cad: number
        policy_check_id: string | null
        risk_score_id: string | null
        ai_recommendation: Json | null
        review_queue_item_id: string | null
        context_snapshot: Json
        recommendation_source: 'deterministic_fallback' | 'openai_structured_output'
        recommendation_generated_at: string | null
        requester_note: string | null
        decision_note: string | null
        decided_by: string | null
        decided_at: string | null
        created_at: string
        updated_at: string
      }>
      expense_reports: TableDef<{
        id: string
        employee_id: string
        department_id: string
        period_start: string
        period_end: string
        status: 'draft' | 'generated' | 'exported' | 'archived'
        total_amount_cad: number
        missing_receipt_count: number
        policy_flag_count: number
        risk_flag_count: number
        report_name: string | null
        report_spec: Json
        workflow_status: 'scan_incomplete' | 'action_required' | 'pending_cfo_review' | 'ready_for_cfo'
        workflow_snapshot: Json
        ai_summary: string | null
        synthetic: boolean
        created_at: string
        updated_at: string
      }>
      expense_report_items: TableDef<{
        id: string
        report_id: string
        transaction_id: string
        amount_cad: number
        category: string
        policy_status: string | null
        risk_level: string | null
        review_queue_item_id: string | null
        approval_request_id: string | null
        approval_recommendation: Json | null
        reviewer_next_action: string | null
        created_at: string
      }>
      policy_documents: TableDef<{
        id: string
        title: string
        version: string
        source_type: string
        content: string
        file_name: string | null
        storage_path: string | null
        raw_text: string | null
        extracted_text: string | null
        extraction_status: string
        extraction_error: string | null
        synthetic: boolean
        active: boolean
        created_at: string
        updated_at: string
      }>
      policy_extraction_runs: TableDef<{
        id: string
        policy_document_id: string
        model_used: string | null
        status: string
        summary: string | null
        ambiguities: Json
        unsupported_or_missing_fields: Json
        suggested_feature_engineering: Json
        draft_rule_count: number
        error: string | null
        created_at: string
      }>
      review_queue_items: TableDef<{
        id: string
        transaction_id: string
        employee_id: string | null
        department_id: string | null
        transaction_date: string | null
        merchant: string | null
        amount_cad: number
        category: string
        queue_status: 'open' | 'in_approval' | 'resolved' | 'ignored'
        review_priority: number
        review_level: 'low' | 'medium' | 'high' | 'critical'
        policy_check_id: string | null
        policy_status: string | null
        policy_severity: 'low' | 'medium' | 'high' | 'critical' | null
        policy_flags: Json
        risk_score_id: string | null
        risk_score: number
        risk_level: 'low' | 'medium' | 'high' | 'critical' | null
        risk_signals: Json
        ai_context: string | null
        next_action: string
        reviewer_brief: Json | null
        generated_at: string
        created_at: string
        updated_at: string
      }>
      policy_chunks: TableDef<{
        id: string
        document_id: string
        rule_code: string | null
        chunk_index: number
        content: string
        metadata: Json
        synthetic: boolean
        created_at: string
      }>
      audit_log: TableDef<{
        id: string
        actor_employee_id: string | null
        action: string
        entity_type: string
        entity_id: string | null
        details: Json
        created_at: string
      }>
      chat_sessions: TableDef<{
        id: string
        title: string
        created_by_employee_id: string | null
        created_at: string
        updated_at: string
      }>
      chat_messages: TableDef<{
        id: string
        session_id: string
        role: 'user' | 'assistant' | 'system' | 'tool'
        content: string
        metadata: Json
        created_at: string
      }>
    }
    Views: Record<string, never>
    Functions: {
      match_policy_chunks: {
        Args: {
          query_embedding: string
          match_threshold: number
          match_count: number
        }
        Returns: {
          id: string
          document_id: string
          rule_code: string | null
          content: string
          similarity: number
        }[]
      }
    }
    Enums: Record<string, never>
    CompositeTypes: Record<string, never>
  }
}
