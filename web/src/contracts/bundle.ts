/* Generated from contracts/schemas/match_bundle.schema.json. Do not edit: run `npm run gen:types`. */

export type ClaimId = string;
/**
 * event_ids / match refs that support it.
 */
export type Evidence = string[];
/**
 * True for hand-written fixture data (not simulated).
 */
export type Illustrative = boolean;
export type IntervalHigh = number | null;
export type IntervalLow = number | null;
export type Label = string | null;
export type LeagueRef = number | null;
export type Metric = string;
export type Minute = number | null;
export type N = number | null;
export type PlayerId = string | null;
export type Status = "sufficient" | "insufficient";
export type Target = string | null;
export type Team = string | null;
export type Type =
  | "observed_tendency"
  | "observed_adaptation"
  | "observed_mechanism"
  | "sim_valuation"
  | "sim_matrix_cell"
  | "opponent_estimate"
  | "regret"
  | "kpi_status";
export type Unit = string | null;
export type Value = number | string;
export type Claims = Claim[];
export type Claims1 = string[];
export type CueId = string;
/**
 * @minItems 1
 */
export type Mode = ["casual" | "analyst", ...("casual" | "analyst")[]];
export type Priority = number;
export type TMatch = string;
export type Team1 = string | null;
export type Template =
  | "plan_card"
  | "plan_sealed"
  | "plan_tracker_lt"
  | "plan_alert"
  | "adaptation_detected"
  | "plan_b_fired"
  | "duel_rooms"
  | "duel_sealed"
  | "duel_reveal"
  | "duel_matrix"
  | "plan_scorecard"
  | "bench_regret"
  | "option_not_taken"
  | "goal_flash";
export type En = string;
export type Es = string;
export type TtlS = number;
export type Cues = Cue[];
export type BestResponse = string;
export type Chosen = string;
export type ClaimId1 = string | null;
export type OpponentChosen = string;
/**
 * xPts(best response) - xPts(chosen) on the true matrix; >= 0.
 */
export type RegretXpts = number;
export type Team2 = string;
export type OptionId = string;
export type Rule = "safe_pick" | "best_guess" | "gamble";
export type Salt = string;
export type Team3 = string;
export type R = number;
/**
 * Owner of a believed matrix; null for true.
 */
export type Believer = string | null;
export type ClaimId2 = string | null;
export type Cells = Cell[][];
/**
 * Believed matrices: the believer's probabilities over the opponent options.
 */
export type ColProbs = number[] | null;
export type ColTeam = string;
/**
 * Column option_ids; cols[0] is Stay.
 *
 * @minItems 2
 * @maxItems 3
 */
export type Cols = [string, string] | [string, string, string];
export type Illustrative1 = boolean;
export type Kind = "believed" | "true";
export type MatchId = string;
export type MatrixId = string;
/**
 * Only when column probabilities are known.
 */
export type BestGuess = string | null;
export type Dominant = string | null;
export type Gamble = string | null;
export type SafePick = string;
export type Team4 = string;
export type RowTeam = string;
/**
 * Row option_ids; rows[0] is Stay.
 *
 * @minItems 2
 * @maxItems 3
 */
export type Rows = [string, string] | [string, string, string];
export type Seed = number;
export type Illustrative2 = boolean;
export type MatchId1 = string;
export type Minute1 = number;
export type SealedAt = string;
export type Sha256 = string;
export type Team5 = string;
export type Claims2 = string[];
export type Estimator = string;
export type Opponent = string;
/**
 * @minItems 2
 * @maxItems 3
 */
export type Options = [EstimatedOption, EstimatedOption] | [EstimatedOption, EstimatedOption, EstimatedOption];
/**
 * True when this is an analyst's guess of the OPPONENT.
 */
export type Estimated = boolean;
/**
 * claim_ids that justify the option.
 */
export type Evidence1 = string[];
export type Intent =
  | "stay_the_course"
  | "press_higher"
  | "drop_block"
  | "go_direct"
  | "short_build_up"
  | "attacking_subs"
  | "protect_lead"
  | "target_weak_side";
export type AttackChannel = ("left" | "center" | "right" | "balanced") | null;
export type BuildUp = ("short" | "mixed" | "direct") | null;
export type CornerDelivery = ("near_post" | "far_post" | "short") | null;
export type PressHeight = ("high" | "mid" | "low") | null;
export type PressTarget = string | null;
export type OptionId1 = string;
/**
 * @maxItems 3
 */
export type Subs = [] | [Sub] | [Sub, Sub] | [Sub, Sub, Sub];
export type In = string;
export type Out = string;
/**
 * 'HT' or a minute window like '60-65'.
 */
export type Window = string;
export type Team6 = string;
export type Probability = number;
/**
 * options[0] is Stay the course.
 *
 * @minItems 2
 * @maxItems 3
 */
export type Options1 = [Option, Option] | [Option, Option, Option];
export type Team7 = string;
export type BodyPart = ("right_foot" | "left_foot" | "head" | "other") | null;
export type EndX = number | null;
export type EndY = number | null;
export type EventId = string;
export type MatchId2 = string;
export type Minute2 = number;
export type Outcome =
  | (
      | "success"
      | "fail"
      | "goal"
      | "saved"
      | "off_target"
      | "blocked"
      | "won"
      | "lost"
      | "first_contact_won"
      | "first_contact_lost"
    )
  | null;
export type Period = 1 | 2;
export type PlayerId1 = string | null;
export type PossessionId = number;
export type ReceiverId = string | null;
/**
 * Links shots/goals to the corner that created them.
 */
export type SetPieceRef = string | null;
/**
 * Only for type == 'sub'.
 */
export type SubIn = string | null;
/**
 * Only for type == 'sub'.
 */
export type SubOut = string | null;
/**
 * Match clock in seconds since kick-off (second half starts at 2700).
 */
export type T = number;
export type Team8 = string;
export type Type1 =
  | "pass"
  | "long_ball"
  | "cross"
  | "carry"
  | "shot"
  | "goal"
  | "pressure"
  | "tackle"
  | "interception"
  | "clearance"
  | "foul"
  | "corner"
  | "goal_kick"
  | "throw_in"
  | "kick_off"
  | "sub"
  | "possession_change"
  | "recovery";
export type UnderPressure = boolean;
export type X = number;
export type Y = number;
/**
 * Absolute zone = band * 3 + lane (see contracts.common).
 */
export type Zone = number;
export type Events = Event[];
/**
 * True for fixture bundles (hand-made, not simulated).
 */
export type Illustrative3 = boolean;
/**
 * @minItems 2
 * @maxItems 2
 */
export type Attack = [AttackDirection, AttackDirection];
export type Period1 = 1 | 2;
/**
 * Team attacking towards x = 105 in this period.
 */
export type PositiveX = string;
export type Away = string;
export type Competition = string;
export type Home = string;
export type KickoffLabel = string;
export type MatchId3 = string;
/**
 * The demo bundle is precomputed; the UI must say so.
 */
export type Precomputed = boolean;
export type Synthetic = true;
/**
 * @minItems 1
 * @maxItems 6
 */
export type Kpis =
  | [Kpi]
  | [Kpi, Kpi]
  | [Kpi, Kpi, Kpi]
  | [Kpi, Kpi, Kpi, Kpi]
  | [Kpi, Kpi, Kpi, Kpi, Kpi]
  | [Kpi, Kpi, Kpi, Kpi, Kpi, Kpi];
export type ByMinute = number;
export type Id = string;
export type Metric1 = "high_turnovers" | "final_third_entries_share" | "set_piece_xg" | "balls_in_behind_conceded";
export type Target1 = string;
export type AttackChannel1 = "left" | "center" | "right" | "balanced";
export type BuildUp1 = "short" | "mixed" | "direct";
export type CornerDelivery1 = "near_post" | "far_post" | "short";
export type PressHeight1 = "high" | "mid" | "low";
/**
 * Opponent player_id, or null for none.
 */
export type PressTarget1 = string | null;
export type Opponent1 = string;
export type AfterMinute = number | null;
export type Kpi1 = string | null;
export type ScoreDiff = string | null;
export type Status1 = ("on_track" | "at_risk" | "failing" | "insufficient_evidence") | null;
export type Subs1 = Sub[];
export type PlanB = PlanBRule[];
export type PlanId = string;
export type At = string;
export type Sha2561 = string;
/**
 * @maxItems 5
 */
export type SubsPlan = [] | [Sub] | [Sub, Sub] | [Sub, Sub, Sub] | [Sub, Sub, Sub, Sub] | [Sub, Sub, Sub, Sub, Sub];
export type Team9 = string;
/**
 * claim_id of the sim_valuation claim.
 */
export type Valuation = string | null;
/**
 * @minItems 2
 * @maxItems 2
 */
export type Ball = [unknown, unknown];
export type T1 = number;
export type RenderFrames = RenderFrame[];
export type SchemaVersion = string;
/**
 * @maxItems 5
 */
export type Findings =
  | []
  | [FindingRef]
  | [FindingRef, FindingRef]
  | [FindingRef, FindingRef, FindingRef]
  | [FindingRef, FindingRef, FindingRef, FindingRef]
  | [FindingRef, FindingRef, FindingRef, FindingRef, FindingRef];
export type ClaimId3 = string;
/**
 * Text with {claim_id.field} placeholders, verified by code.
 */
export type Headline = string;
export type Model = string;
export type Opponent2 = string;
export type Claims3 = string[];
export type Confidence = number;
export type Estimator1 = string;
export type Opponent3 = string;
export type Team10 = string;
export type BandHigh = number | null;
export type BandLow = number | null;
export type ClaimId4 = string | null;
/**
 * Mean of pre-match sims at this minute.
 */
export type Expected = number | null;
export type KpiId = string;
export type N1 = number;
export type PlanId1 = string;
export type Status2 = "on_track" | "at_risk" | "failing" | "insufficient_evidence";
export type Team11 = string;
export type Value1 = number;
export type Kpis1 = KpiStatus[];
export type MatchId4 = string;
export type Minute3 = number;
export type Period2 = 1 | 2;
export type Snapshots = Snapshot[];
export type Name = string;
/**
 * @minItems 11
 */
export type Players1 = [
  Player,
  Player,
  Player,
  Player,
  Player,
  Player,
  Player,
  Player,
  Player,
  Player,
  Player,
  ...Player[]
];
export type Aerial = number;
export type Finishing = number;
export type Pace = number;
export type Passing = number;
export type PressResistance = number;
export type Stamina = number;
export type Name1 = string;
export type PlayerId2 = string;
export type Position = "GK" | "RB" | "CB" | "LB" | "DM" | "CM" | "AM" | "RW" | "LW" | "ST";
export type Shirt = number;
export type Starter = boolean;
export type ShortName = string;
export type Team12 = string;
export type Agent = "analyst" | "manager" | "director" | "chronicler" | "localizer" | "validator";
export type DurationMs = number;
export type Message = string | null;
export type ResultClaims = string[];
export type Scope = string;
export type Status3 = "ok" | "rejected" | "retried" | "fallback";
export type Step = number;
export type Tool = string | null;
export type TraceId = string;
export type Workflow = "prematch" | "live" | "duel" | "final";
export type Traces = TraceStep[];

export interface MatchBundle {
  claims: Claims;
  cues: Cues;
  duel: Duel | null;
  eval: Eval;
  events: Events;
  illustrative: Illustrative3;
  meta: MatchMeta;
  plans: Plans;
  render_frames: RenderFrames;
  schema_version: SchemaVersion;
  scouting: Scouting;
  snapshots: Snapshots;
  squads: Squads;
  traces: Traces;
}
export interface Claim {
  claim_id: ClaimId;
  evidence: Evidence;
  illustrative: Illustrative;
  interval_high: IntervalHigh;
  interval_low: IntervalLow;
  label: Label;
  league_ref: LeagueRef;
  metric: Metric;
  minute: Minute;
  n: N;
  player_id: PlayerId;
  status: Status;
  target: Target;
  team: Team;
  type: Type;
  unit: Unit;
  value: Value;
}
export interface Cue {
  claims: Claims1;
  cue_id: CueId;
  fields: Fields;
  mode: Mode;
  priority: Priority;
  t_match: TMatch;
  team: Team1;
  template: Template;
  text: I18NText;
  ttl_s: TtlS;
}
export interface Fields {
  [k: string]: string;
}
export interface I18NText {
  en: En;
  es: Es;
}
export interface Duel {
  broadcast: DuelBroadcast;
  illustrative: Illustrative2;
  match_id: MatchId1;
  minute: Minute1;
  private: Private;
}
export interface DuelBroadcast {
  regret: Regret;
  revealed: Revealed;
  true_matrix: Matrix;
}
export interface Regret {
  [k: string]: Regret1;
}
/**
 * This interface was referenced by `Regret`'s JSON-Schema definition
 * via the `patternProperty` "^[A-Z]{3}$".
 */
export interface Regret1 {
  best_response: BestResponse;
  chosen: Chosen;
  claim_id: ClaimId1;
  opponent_chosen: OpponentChosen;
  regret_xpts: RegretXpts;
  team: Team2;
}
export interface Revealed {
  [k: string]: RevealedChoice;
}
/**
 * This interface was referenced by `Revealed`'s JSON-Schema definition
 * via the `patternProperty` "^[A-Z]{3}$".
 */
export interface RevealedChoice {
  option_id: OptionId;
  rule: Rule;
  salt: Salt;
  team: Team3;
}
export interface Matrix {
  R: R;
  believer: Believer;
  cells: Cells;
  col_probs: ColProbs;
  col_team: ColTeam;
  cols: Cols;
  illustrative: Illustrative1;
  kind: Kind;
  match_id: MatchId;
  matrix_id: MatrixId;
  readings: Readings;
  row_team: RowTeam;
  rows: Rows;
  seed: Seed;
}
export interface Cell {
  ci90: Ci90;
  claim_id: ClaimId2;
  xpts: Xpts;
}
export interface Ci90 {
  /**
   * @minItems 2
   * @maxItems 2
   *
   * This interface was referenced by `Ci90`'s JSON-Schema definition
   * via the `patternProperty` "^[A-Z]{3}$".
   */
  [k: string]: [unknown, unknown];
}
export interface Xpts {
  /**
   * This interface was referenced by `Xpts`'s JSON-Schema definition
   * via the `patternProperty` "^[A-Z]{3}$".
   */
  [k: string]: number;
}
export interface Readings {
  [k: string]: MatrixReading;
}
/**
 * How one team reads the matrix (computed in code, see engine.duel).
 *
 * This interface was referenced by `Readings`'s JSON-Schema definition
 * via the `patternProperty` "^[A-Z]{3}$".
 */
export interface MatrixReading {
  best_guess: BestGuess;
  best_response: BestResponse1;
  dominant: Dominant;
  gamble: Gamble;
  safe_pick: SafePick;
  team: Team4;
}
/**
 * Opponent option_id -> this team's best option_id.
 */
export interface BestResponse1 {
  [k: string]: string;
}
export interface Private {
  [k: string]: TeamDuelPrivate;
}
/**
 * This interface was referenced by `Private`'s JSON-Schema definition
 * via the `patternProperty` "^[A-Z]{3}$".
 */
export interface TeamDuelPrivate {
  believed_matrix: Matrix;
  choice: SealedChoice;
  opponent_estimate: OpponentOptionsEstimate;
  options: Options1;
  team: Team7;
}
/**
 * Commit only: the option and salt stay hidden until the reveal (see contracts.sealing).
 */
export interface SealedChoice {
  sealed_at: SealedAt;
  sha256: Sha256;
  team: Team5;
}
export interface OpponentOptionsEstimate {
  claims: Claims2;
  estimator: Estimator;
  opponent: Opponent;
  options: Options;
}
export interface EstimatedOption {
  option: Option;
  probability: Probability;
}
export interface Option {
  estimated: Estimated;
  evidence: Evidence1;
  intent: Intent;
  label: I18NText;
  lever_changes: LeverChanges;
  option_id: OptionId1;
  subs: Subs;
  team: Team6;
}
/**
 * Partial levers: only the fields an option or a Plan B rule changes.
 */
export interface LeverChanges {
  attack_channel: AttackChannel;
  build_up: BuildUp;
  corner_delivery: CornerDelivery;
  press_height: PressHeight;
  press_target: PressTarget;
}
export interface Sub {
  in: In;
  out: Out;
  window: Window;
}
/**
 * Aggregated E1..E8 results for the panel.
 */
export interface Eval {
  [k: string]: unknown;
}
export interface Event {
  body_part: BodyPart;
  end_x: EndX;
  end_y: EndY;
  event_id: EventId;
  match_id: MatchId2;
  minute: Minute2;
  outcome: Outcome;
  period: Period;
  player_id: PlayerId1;
  possession_id: PossessionId;
  receiver_id: ReceiverId;
  set_piece_ref: SetPieceRef;
  sub_in: SubIn;
  sub_out: SubOut;
  t: T;
  team: Team8;
  type: Type1;
  under_pressure: UnderPressure;
  x: X;
  y: Y;
  zone: Zone;
}
export interface MatchMeta {
  attack: Attack;
  away: Away;
  competition: Competition;
  home: Home;
  kickoff_label: KickoffLabel;
  match_id: MatchId3;
  precomputed: Precomputed;
  synthetic: Synthetic;
}
export interface AttackDirection {
  period: Period1;
  positive_x: PositiveX;
}
export interface Plans {
  [k: string]: Plan;
}
/**
 * This interface was referenced by `Plans`'s JSON-Schema definition
 * via the `patternProperty` "^[A-Z]{3}$".
 */
export interface Plan {
  kpis: Kpis;
  lever_evidence: LeverEvidence;
  levers: Levers;
  name: I18NText;
  opponent: Opponent1;
  plan_b: PlanB;
  plan_id: PlanId;
  sealed: Seal | null;
  subs_plan: SubsPlan;
  team: Team9;
  valuation: Valuation;
}
export interface Kpi {
  by_minute: ByMinute;
  id: Id;
  metric: Metric1;
  params: Params;
  target: Target1;
}
export interface Params {
  [k: string]: string;
}
/**
 * Lever name -> claim_ids. Every non-default lever needs one.
 */
export interface LeverEvidence {
  [k: string]: string[];
}
/**
 * This interface was referenced by `ActiveLevers`'s JSON-Schema definition
 * via the `patternProperty` "^[A-Z]{3}$".
 */
export interface Levers {
  attack_channel: AttackChannel1;
  build_up: BuildUp1;
  corner_delivery: CornerDelivery1;
  press_height: PressHeight1;
  press_target: PressTarget1;
}
export interface PlanBRule {
  if: PlanBCondition;
  then: PlanBAction;
}
export interface PlanBCondition {
  after_minute: AfterMinute;
  kpi: Kpi1;
  score_diff: ScoreDiff;
  status: Status1;
}
export interface PlanBAction {
  levers: LeverChanges;
  subs: Subs1;
}
/**
 * Commit of the canonical plan JSON (everything except `sealed`). See contracts.sealing.
 */
export interface Seal {
  at: At;
  sha256: Sha2561;
}
/**
 * Visual layer only (ball-anchored shapes). No metric is computed from these positions.
 */
export interface RenderFrame {
  ball: Ball;
  players: Players;
  t: T1;
}
export interface Players {
  /**
   * @minItems 2
   * @maxItems 2
   */
  [k: string]: [unknown, unknown];
}
export interface Scouting {
  [k: string]: ScoutingSummary;
}
/**
 * What a bench's analyst reported before kick-off (findings point to claims in `claims`).
 *
 * This interface was referenced by `Scouting`'s JSON-Schema definition
 * via the `patternProperty` "^[A-Z]{3}$".
 */
export interface ScoutingSummary {
  findings: Findings;
  model: Model;
  opponent: Opponent2;
  opponent_estimate: OpponentPlanEstimate | null;
  team: Team10;
}
export interface FindingRef {
  claim_id: ClaimId3;
  headline: Headline;
}
/**
 * Pre-match: the analyst's guess of the opponent's levers (never the opponent's real plan).
 */
export interface OpponentPlanEstimate {
  claims: Claims3;
  confidence: Confidence;
  estimator: Estimator1;
  levers: Levers;
  opponent: Opponent3;
}
export interface Snapshot {
  active_levers: ActiveLevers;
  condition_est: ConditionEst;
  kpis: Kpis1;
  match_id: MatchId4;
  minute: Minute3;
  on_pitch: OnPitch;
  period: Period2;
  score: Score;
  sub_windows_used: SubWindowsUsed;
  subs_used: SubsUsed;
}
export interface ActiveLevers {
  [k: string]: Levers;
}
/**
 * player_id -> 0..1 (estimate).
 */
export interface ConditionEst {
  [k: string]: number;
}
export interface KpiStatus {
  band_high: BandHigh;
  band_low: BandLow;
  claim_id: ClaimId4;
  expected: Expected;
  kpi_id: KpiId;
  n: N1;
  plan_id: PlanId1;
  status: Status2;
  team: Team11;
  value: Value1;
}
export interface OnPitch {
  /**
   * This interface was referenced by `OnPitch`'s JSON-Schema definition
   * via the `patternProperty` "^[A-Z]{3}$".
   */
  [k: string]: string[];
}
export interface Score {
  /**
   * This interface was referenced by `Score`'s JSON-Schema definition
   * via the `patternProperty` "^[A-Z]{3}$".
   */
  [k: string]: number;
}
export interface SubWindowsUsed {
  /**
   * This interface was referenced by `SubWindowsUsed`'s JSON-Schema definition
   * via the `patternProperty` "^[A-Z]{3}$".
   */
  [k: string]: number;
}
export interface SubsUsed {
  /**
   * This interface was referenced by `SubsUsed`'s JSON-Schema definition
   * via the `patternProperty` "^[A-Z]{3}$".
   */
  [k: string]: number;
}
export interface Squads {
  teams: Teams;
}
export interface Teams {
  [k: string]: Squad;
}
/**
 * This interface was referenced by `Teams`'s JSON-Schema definition
 * via the `patternProperty` "^[A-Z]{3}$".
 */
export interface Squad {
  name: Name;
  players: Players1;
  short_name: ShortName;
  team: Team12;
}
export interface Player {
  attributes: Attributes;
  name: Name1;
  player_id: PlayerId2;
  position: Position;
  shirt: Shirt;
  starter: Starter;
}
export interface Attributes {
  aerial: Aerial;
  finishing: Finishing;
  pace: Pace;
  passing: Passing;
  press_resistance: PressResistance;
  stamina: Stamina;
}
export interface TraceStep {
  agent: Agent;
  args: Args;
  duration_ms: DurationMs;
  message: Message;
  result_claims: ResultClaims;
  scope: Scope;
  status: Status3;
  step: Step;
  tool: Tool;
  trace_id: TraceId;
  workflow: Workflow;
}
export interface Args {
  [k: string]: unknown;
}
