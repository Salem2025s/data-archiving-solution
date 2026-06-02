"""
Term base for keyword-based domain pre-classification of data assets.

Terms are drawn from three sources:
  1. PeopleSoft column names observed in column_names_text (Oracle EP92U038)
  2. Semantic labels found in column_value_semantics_text
  3. General FR/EN business vocabulary

Architecture note:
  This dict (DOMAIN_TERMS) is used ONLY by the keyword pre-classification
  step in score_business_domain.py (_keyword_classify).
  It is intentionally separate from DOMAIN_KEYWORDS, which feeds ML numeric
  features and must remain frozen until the model is retrained.

Paie (payroll) terms are merged into the "hr" bucket per project convention.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Domain term lists
# Keys must be a subset of KEYWORD_TO_LABEL keys defined below.
# ---------------------------------------------------------------------------
DOMAIN_TERMS: dict[str, list[str]] = {
    # -----------------------------------------------------------------------
    # Finance & Contrôle
    # GL, journal, budget, payment / banking, chartfields, reconciliation
    # -----------------------------------------------------------------------
    "finance": [
        # PeopleSoft GL / journal identifiers
        "account", "acct", "acctg", "accounting", "accounting_dt",
        "accounting_period", "altacct",
        "journal", "journal_id", "journal_date", "journal_line",
        "jrnl", "jrnl_ln_ref", "appl_jrnl",
        "ledger", "ledger_group",
        "gl", "gl_distrib_status",
        # Budget and commitment control (KK module)
        "budget", "budget_ref", "budget_dt", "budget_hdr_status",
        "budget_line_status", "fiscal_year", "kk",
        # Amounts and currencies
        "amount", "amt", "monetary_amount", "foreign_amount",
        "statistic_amount", "amt_adj", "amt_rem", "amt_sel",
        "bank_acct_rvl_amt", "wo_item_amt", "amt_allocated",
        "currency_cd", "currency", "foreign_currency", "payment_currency",
        "pymt_rate_div", "pymt_rate_mult", "pymt_rt_type",
        "rate_div", "rate_mult", "rt_type",
        # Payment and banking
        "payment", "payment_amt", "payment_id", "payment_method",
        "payment_status", "payment_seq_num",
        "deposit", "deposit_id", "deposit_bu",
        "bank_account_num", "bnk_id_nbr",
        "cashcntl_flag", "cash_cntrl_done", "cash_cntrl_use",
        "eft_file_nbr",
        "disc_earned", "disc_taken", "disc_unearned",
        "lockbox_pymnt_id",
        # GL chartfields and allocation
        "chartfield1", "chartfield2", "chartfield3",
        "class_fld", "fund_code", "program_code", "project_id",
        "operating_unit", "business_unit_gl", "business_unit_pc",
        "resource_category", "resource_sub_cat", "resource_type",
        "statistics_code", "unit_of_measure",
        "qty_allocated",
        # Document and reconciliation
        "doc_seq_date", "doc_seq_nbr", "doc_seq_status", "doc_type",
        "entry_event", "open_item_key",
        "reconcile_dt", "recon_cycle_nbr", "recon_status", "recon_type",
        "debit_credit", "analysis_type",
        # Tax, revenue, cost — FR/EN
        "invoice", "facture", "tax", "tva", "vat",
        "expense", "revenue", "cost", "deprec",
        "comptabil", "compte", "montant", "devise",
        "ap", "ar", "fi", "glacct", "treasur",
        "voucher", "setid",
        # Semantic labels from column_value_semantics_text
        "financial_amount", "percentage_or_rate",
    ],

    # -----------------------------------------------------------------------
    # RH — Ressources Humaines  (Paie / Payroll terms merged here)
    # Employee, job, training, compensation, absence, payroll
    # -----------------------------------------------------------------------
    "hr": [
        # Core PeopleSoft employee identifier
        "emplid",
        # Job and organisation
        "job_code", "position_nbr", "empl_type", "empl_status", "empl_class",
        "deptid",
        # Training, education, certifications
        "accomplishment", "educator", "school", "school_code",
        "major", "major_code", "gpa",
        "terminal_degree", "graduate_indicator",
        "yr_acquired", "dt_issued",
        "read_proficiency", "speak_proficiency", "write_proficiency",
        "native_language", "teacher", "grantor",
        "mandate", "mandate_function", "mandate_begin_date", "mandate_end_date",
        "license_nbr", "license_verified",
        "average_grade", "practic_grade_ger", "theory_grade_ger",
        "gvt_cred_hrs_type", "gvt_credit_hours", "ipe_sw",
        "issued_by", "renewal", "passed", "select_cmp",
        "translator",
        # Compensation
        "comp_rate", "comp_freq", "hourly_rt", "salary_admin_plan",
        # Benefits
        "ben_plan", "coverage_cd",
        # Absence
        "absence_type",
        # ---- Paie / Payroll (merged into HR) ----
        "paygroup", "pay_group",
        "paycheck", "check_dt",
        "gross_pay", "net_pay", "total_gross",
        "ded_calc", "ded_class",
        "erncd", "earn_code",
        "ded_code", "tax_ded",
        "soc_sec", "medicare",
        "pay_sheet", "pay_line",
        "pay_oth_earns",
        "overtime", "regular_pay",
        "paie", "cotisation", "bulletin_paie",
        "salaire_brut", "salaire_net",
        # General EN/FR
        "employee", "empl", "job", "manager", "payroll",
        "position", "hire", "worker", "salary", "person", "headcount",
        "compensation", "benefit", "pay", "leave",
        "employe", "salaire", "poste", "conge",
        "recrutement", "formation",
        # Semantic labels from column_value_semantics_text
        "person_identifier", "person_first_name",
        "person_last_name", "person_full_name",
        "job_label",
    ],

    # -----------------------------------------------------------------------
    # IT & Sécurité  (PeopleSoft: Technique / admin tables)
    # User access, roles, permissions, process scheduler, audit
    # -----------------------------------------------------------------------
    "it": [
        # PeopleSoft operator / authentication
        "oprid", "oprclass", "objectownerid",
        "access_group", "active_flag",
        "run_cntl_id",
        "language_option", "system_defined",
        # File and batch processing
        "file_extension", "output_filename",
        "dfi_id_bank_opt", "fedrl_eft_ach_ind",
        "max_files", "last_eft_file_id",
        # Audit
        "audit_actn", "audit_stamp",
        # PeopleSoft menu / portal
        "portal", "menu", "psmenu",
        # General EN/FR
        "user", "role", "access", "auth", "permission", "config",
        "server", "system", "login", "application", "security",
        "sysadm", "page", "xlat", "dbowner", "prcs", "audit",
        # Semantic labels from column_value_semantics_text
        "user_identifier", "processing_identifier",
    ],

    # -----------------------------------------------------------------------
    # Achats & Fournisseurs  (Procurement)
    # Purchase orders, vendors, sourcing, contracts, RFQ, auction
    # -----------------------------------------------------------------------
    "procurement": [
        # PeopleSoft PO-specific column names (strong, unique signals)
        "vendor_id", "vndr_id",
        "po_id", "po_line", "po_hdr_status",
        "business_unit_po",
        "match_cntrl_id", "mtch_excptn_type", "match_rule_id",
        "contract_id", "contract_line_num",
        "rfq_id", "rfq_line",
        "shipto_id", "buyer_id",
        "item_id",
        # Sourcing / auction (PeopleSoft eProcurement)
        "auc_id", "auc_round", "auc_version", "auc_group_id",
        "auc_award_nbr", "auc_award_qty",
        # Blanket PO
        "bpo",
        # Receiving
        "recv_ln_nbr", "recv_qty",
        # General EN/FR
        "vendor", "supplier", "purchase", "po",
        "sourcing", "rfq", "contract",
        "fournisseur", "achat", "commande",
    ],

    # -----------------------------------------------------------------------
    # Ventes & Clients  (Sales / AR / Billing / Order Management)
    # Customers, accounts receivable, billing, sales orders
    # -----------------------------------------------------------------------
    "sales": [
        # PeopleSoft AR / customer identifiers
        "cust_id", "customer_id", "corporate_cust_id",
        "remit_from_cust_id",
        "bill_to_cust_id",
        "subcust_qual1", "subcust_qual2",
        "micr_id",
        # Billing-specific (PS_BI_* module)
        "invoice_dt", "bi_currency_cd",
        "business_unit_om",
        # AR-specific columns
        "entry_type",
        "asof_dt",
        "line_seq_num",
        "item_line",
        "address_seq_num",
        # AR aging and collections
        "aging_category", "aging_type",
        "collection_status", "collection_aging",
        "deduction_status",
        "draft_status",
        # Sales order management
        "order_no",
        # General EN/FR
        # Note: "name1" removed — too generic (vendor name, employee name,
        # shipping party name all use NAME1 in PeopleSoft).
        "customer", "client", "opportunity", "quote", "deal", "crm",
        "sales", "pipeline", "booking",
        "vente", "facturation",
        # Semantic labels from column_value_semantics_text
        "postal_location",
    ],

    # -----------------------------------------------------------------------
    # Marketing  →  mapped to "Ventes & Clients" label
    # Note: "segment" removed — matches PeopleSoft ChartField SEGMENT (GL).
    # Note: "contact_id" and "cntct_seq_num" removed — appear in AR customer
    # statement tables (PS_STMT_CUST_*), causing false positives.
    # Marketing is genuinely sparse in this PeopleSoft instance.
    # -----------------------------------------------------------------------
    "marketing": [
        # Campaign / promotion-specific
        "campaign_id", "mkt_segment",
        "lead_id", "promo_cd", "promo_code",
        "ra_item_cnt",
        # General EN/FR
        "campaign", "lead", "audience",
        "click", "impression", "conversion", "promo",
    ],

    # -----------------------------------------------------------------------
    # Risk / Contrôle  →  mapped to "Finance & Contrôle" label
    # Note: "issue" removed — matches publication issue numbers, not GRC.
    # Note: "key*_fldname/fld_val" removed — generic PeopleSoft key-value
    # config pattern appears in procurement, system, and VAT tables, not risk.
    # Note: "eo_audit_flg", "exception_info" kept — more specific signals.
    # -----------------------------------------------------------------------
    "risk": [
        # PeopleSoft GRC audit signals (more specific than key*_fldname)
        "eo_audit_flg",
        "exception_info",
        "exception_status",
        # GRC-specific terms
        "grc", "sox", "internal_control",
        "audit_finding", "risk_assessment", "risk_score",
        "mitigation_plan",
        # General EN/FR
        "risk", "compliance", "incident",
        "mitigation", "conformite",
    ],

    # -----------------------------------------------------------------------
    # Supply Chain / Logistique / Production
    # Warehouse, inventory, BOM, production, transport, shipping
    # -----------------------------------------------------------------------
    "supply_chain": [
        # PeopleSoft inventory / BOM identifiers (strong, unique)
        "inv_item_id", "inv_lot_id",
        "bom_code", "bom_state",
        "storage_area", "stor_level_1", "stor_level_2",
        "serial_id",
        "wh_id",
        # Shipping and carrier
        "carrier_id",
        "consignee_intm", "consignee_ultm",
        "bill_of_lading",
        "freight_terms", "freight_charge",
        "ship_cntr_id",
        "gross_weight",
        "unit_measure_wt", "unit_measure_vol",
        "ship_type_id",
        "ship_to_cust_id",
        # Order fulfillment / demand
        "demand_line_no", "demand_source",
        "order_int_line_no", "sched_line_nbr",
        # Production / manufacturing
        "production_id", "production_type",
        "prdn_area_code",
        "config_code",
        "rtg_code",
        "planner_cd",
        "source_bus_unit",
        "destin_bu",
        # Production / routing
        "prod_id", "mfg_order", "work_order",
        "route_cd", "routing_cd",
        "op_sequence",
        # General EN/FR
        "shipment", "warehouse", "delivery", "route",
        "transport", "logistics", "bom",
        "livraison", "entrepot", "logistique", "production",
        "plant",
    ],
}

# ---------------------------------------------------------------------------
# Domain key  →  ML model class label
# Must match the label strings used in the production model artifact.
# ---------------------------------------------------------------------------
KEYWORD_TO_LABEL: dict[str, str] = {
    "finance":      "Finance & Contrôle",
    "hr":           "RH",
    "it":           "IT & Sécurité",
    "procurement":  "Achats & Fournisseurs",
    "sales":        "Ventes & Clients",
    "marketing":    "Ventes & Clients",
    "risk":         "Finance & Contrôle",
    "supply_chain": "Supply Chain / Logistique / Production",
}
