// The recorded Microsoft Foundry run (pipeline/foundry_web.py -> public/foundry_run.json): a separate file from the
// match bundle, loaded only by the analyst desk's "Real Microsoft Foundry Run" tab.

export interface FoundryTurn {
  phase: "pre-match" | "half-time";
  club: string;
  role: string;
  output: string;
  response_id: string | null;
  service_model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  tools: string[];
  ms: number;
}

export interface Guardrail {
  club: string;
  agent: string;
  item: string;
  attempts: number;
  rejections: { message: string; plain: string }[];
  outcome: string;
}

export interface BenchDecision {
  choice: string;
  rule: string;
  regret_xpts: number;
  regret_ci90: [number, number];
  best_response: string;
}

export interface ComparisonRow {
  metric: string;
  unit?: string;
  rules: { value: number; ci95?: [number, number] };
  llm: { value: number; ci95?: [number, number] };
  diff: { value: number; ci95: [number, number] };
  significant: boolean;
}

export interface FoundryRun {
  schema: string;
  sources: { evidence: string; evidence_sha256: string; comparison: string | null; comparison_sha256: string | null };
  run: { mode: string; model: string[]; started_utc: string; seconds: number; endpoint_domain: string;
         season_seed: number; match_seed: number; demo_bundle_sha256: string; demo_bundle_unchanged: boolean };
  totals: { model_turns: number; with_service_response_id: number; input_tokens: number; output_tokens: number;
            tool_calls_by_model: number; tools_by_model: Record<string, number> };
  turns: FoundryTurn[];
  guardrails: Guardrail[];
  plans: Record<string, { foundry_plan: string; kpis: string[]; seal_verifies: boolean; demo_plan: string;
                          same_levers_as_demo: boolean; report_attempts: number; findings: number }>;
  halftime: {
    score: Record<string, number>;
    same_as_demo: Record<string, boolean>;
    benches: Record<string, {
      foundry: BenchDecision & { options: { label: string; changes: Record<string, string>; subs: number }[];
                                 distinct: boolean; fell_back_to_rules: boolean };
      demo: BenchDecision & { options: string[] };
    }>;
  };
  comparison: null | {
    title: string;
    design: string;
    rows: ComparisonRow[];
    llm_runs: number;
    cost_eur: number;
    calls: number;
    note: string;
    report: string;
  };
}

export async function loadFoundryRun(url = `${import.meta.env.BASE_URL}foundry_run.json`): Promise<FoundryRun> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load ${url} (${res.status})`);
  return (await res.json()) as FoundryRun;
}
