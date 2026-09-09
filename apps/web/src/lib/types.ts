// Mirrors docs/ARCHITECTURE.md §4. Keep in sync by hand; the engine is the producer.
export type Regime = "trend" | "range" | "compression" | "high_vol" | "event";
export type ExecState = "WATCHING" | "SETUP_FOUND" | "ARMED" | "ORDER_PENDING" | "OPEN" | "EXIT_PENDING" | "CLOSED" | "BLOCKED";
export type BehaviourState = "CALM" | "ELEVATED" | "COOLDOWN" | "RESEARCH";
export type RiskProfile = "conservative" | "standard" | "hard_ceiling";
export type AutomationPermission = "paper_only" | "mentor_only" | "blocked";

export interface Gate { name: string; pass: boolean; reason?: string }
export interface Signal {
  id: string; strategy_id: string; version: number; timestamp: string; symbol: string; regime: Regime;
  side: "long" | "short" | null;
  conditions_passed: string[]; conditions_failed: string[];
  trigger: { type: string; price: number | null; description: string };
  stop: number | null; targets: number[]; quantity: number;
  rupee_risk: number; portfolio_risk_pct: number;
  estimated_costs: number; post_cost_rr: number | null;
  automation_permission: AutomationPermission;
  ambiguity_flags: string[];
  gates: Gate[];
  exec_state: ExecState; verdict: "eligible" | "watch" | "blocked"; sentence: string;
}
export interface RiskStatus {
  trading_bucket: number; one_r: number; profile: RiskProfile;
  daily_used_r: number; daily_limit_r: number; weekly_used_r: number; weekly_limit_r: number;
  concurrent_used_r: number; concurrent_limit_r: number;
  brakes: { daily: boolean; weekly: boolean; concurrent: boolean };
}
export interface DeskSummary {
  risk: RiskStatus;
  behaviour: { state: BehaviourState; reason: string; since: string };
  market: { open: boolean; sim_now: string; session: string };
  watchers: { id: string; strategy_id: string; name: string; exec_state: ExecState; state_reason: string; latest_signal: Signal | null }[];
  provider: "synthetic" | "csv";
}
export interface StageResult { stage: number; name: string; status: "pass" | "fail" | "skip" | "pending"; summary: string; metrics: Record<string, number>; detail: unknown }
export interface ValidationReport {
  strategy_id: string; started_at: string; finished_at: string | null;
  stages: StageResult[]; weakest_stage: number | null; weakest_sentence: string; passed: boolean;
}
export interface JobStatus { id: string; status: "queued" | "running" | "done" | "failed"; current_stage: number; report: ValidationReport | null; error: string | null }
export interface PaperTrade {
  id: string; strategy_id: string; symbol: string; side: "long" | "short"; qty: number;
  planned: { entry: number; stop: number; targets: number[]; risk_r: number };
  actual: { entry: number | null; exit: number | null; entry_ts: string | null; exit_ts: string | null };
  slippage: number; costs: number; mfe_r: number | null; mae_r: number | null;
  exit_reason: string | null; regime: Regime; outcome_r: number | null;
  rules_followed: number; rules_total: number; status: "open" | "closed";
}
export interface JournalAggregates {
  by_regime: Record<string, { trades: number; process_score: number; net_r: number }>;
  streaks: { current: number; longest_win: number; longest_loss: number };
  totals: { trades: number; net_r: number; process_score: number; win_rate: number };
}
export interface Stats { trades: number; wins: number; losses: number; win_rate: number; expectancy_r: number; avg_win_r: number; avg_loss_r: number; profit_factor: number; net_pnl: number; max_drawdown_pct: number; max_drawdown_r: number; largest_trade_share: number; [k: string]: number }
