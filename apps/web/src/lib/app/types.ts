export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface Supplier {
  id: string;
  uploaded_name: string;
  tier: string | null;
  status: string;
  confidence: number | null;
  created_at: string;
  resolved_company_id: number | null;
  company_name: string | null;
  risk_score: string | number | null;
  risk_level: string | null;
  has_sensitive_identifiers: boolean;
}

export interface EventRow {
  id: number;
  source: string;
  event_type: string;
  severity: number;
  occurred_at: string | null;
  reported_at: string;
  title: string;
  summary: string | null;
  url: string | null;
  state: string | null;
  city: string | null;
  cluster_id: number | null;
}

export interface AlertRow {
  id: string;
  supplier_id: string;
  supplier_name: string;
  kind: string;
  status: string;
  assignee_id: string | null;
  detail: string | null;
  rule_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Candidate {
  company_id: number;
  name: string;
  probability: number;
  sources?: string[];
  scores?: { retrieval?: number | null; splink_weight?: number | null; blink?: number | null };
  features?: Record<string, number>;
  comparison?: Record<
    string,
    { uploaded?: string | null; candidate?: string | null; agreement?: string; similarity?: number }
  >;
}

export interface ReviewRow {
  id: string;
  status: string;
  supplier_id: string;
  uploaded_name: string;
  attributes: Record<string, string>;
  tier: string | null;
  candidates: Candidate[];
  created_at: string;
}

export interface Kpi {
  key: string;
  label: string;
  unit: string;
  better: "up" | "down";
  value: number | null;
  previous: number | null;
  change_pct: number | null;
  sparkline?: (number | null)[];
}

export interface Portfolio {
  window: { from: string; to: string };
  demo_data: boolean;
  series_source: string;
  kpis: Kpi[];
  totals: {
    suppliers_by_status: Record<string, number>;
    suppliers_by_level: Record<string, number>;
    events_by_type: Record<string, number>;
    open_alerts: number;
  };
  risk_index_trend: {
    bands: Record<string, number>;
    items: { period: string; risk_index: number }[];
  };
  suppliers_by_level_trend: {
    period: string;
    low: number;
    medium: number;
    high: number;
    critical: number;
  }[];
  events_by_type: { period: string; event_type: string; events: number }[];
  event_source_mix: { source_class: string; events: number }[];
  risk_by_state: { state: string; events: number; weighted_events: number }[];
  facility_events: {
    id: number;
    title: string;
    event_type: string;
    severity: number;
    state: string | null;
    latitude: number;
    longitude: number;
    reported_at: string;
  }[];
  category_heatmap: {
    tier: string;
    event_type: string;
    events: number;
    max_level: string | null;
  }[];
  concentration_by_parent: {
    total_suppliers: number;
    groups: {
      company_id: number;
      name: string;
      suppliers: number;
      share_of_suppliers: number;
      high_risk_suppliers: number;
      share_of_high_risk: number;
      cumulative_share: number;
    }[];
  };
  top_risk_suppliers: {
    supplier_id: string;
    name: string;
    tier: string | null;
    score: string | number;
    level: string;
    last_event: { title: string; reported_at: string } | null;
    change_30d: number | null;
    sparkline: (string | number)[] | null;
  }[];
  disclaimer: string;
  notes: string[];
}

export interface Me2 {
  id: string;
  email: string;
}
