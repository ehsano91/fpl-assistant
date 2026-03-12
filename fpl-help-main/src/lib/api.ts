/**
 * api.ts  —  FPL Assistant API Client
 * -------------------------------------
 * All fetch() calls to the local Python API server live here.
 * The server runs on http://localhost:8000 (engine/api_server.py).
 */

export const API_BASE  = "http://localhost:8000";
export const STALE_TIME = 5 * 60 * 1000;   // 5 minutes

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Position      = "GK" | "DEF" | "MID" | "FWD";
export type FitnessStatus = "fit" | "doubt" | "out";
export type RecType       = "transfer_in" | "transfer_out" | "captain" | "starting_xi" | "chip_alert" | "community_buzz";

export interface Player {
  id:              number;
  name:            string;
  shortName:       string;
  position:        Position;
  team:            string;
  teamCode?:       number;
  xP:              number;
  xPForecast:      number[];
  isCaptain:       boolean;
  isViceCaptain:   boolean;
  fitness:         FitnessStatus;
  opponent?:       string | null;   // opponent short name for upcoming fixture
  isHome?:         boolean | null;
  fdr?:            number | null;   // 1–5 official FPL difficulty
  price?:             number;
  costChangeEvent?:   number;
  costChangeStart?:   number;
  transfersInEvent?:  number;
  transfersOutEvent?: number;
}

export interface SquadResponse {
  gameweek:      number;
  starters:      Player[];
  bench:         Player[];
  points?:       number;       // actual GW points (only for historical GWs)
  isHistorical?: boolean;
  isPlanning?:   boolean;      // true when viewing a future (unplayed) GW
  squadValue?:   number;
  itb?:          number;
}

export interface GWHistory {
  gw:           number;
  points:       number;
  totalPoints:  number;
  overallRank:  number;
}

export interface League {
  id:       number;
  name:     string;
  rank:     number;
  lastRank: number;
}

export interface HistoryResponse {
  history:   GWHistory[];
  currentGW: number;
}

export interface StandingsResponse {
  totalPoints: number;
  overallRank: number;
  swedenRank:  number | null;
  leagues:     League[];
}

export interface Recommendation {
  id:        number;
  type:      RecType;
  title:     string;
  summary:   string;
  reasoning: string;
  positive:  boolean;
}

export interface NewsPill {
  player: string;
  status: "injury" | "returning" | "suspended" | "flagged";
  text:   string;
}

export interface CommunityHeadline {
  source:   string;
  headline: string;
}

export interface HotPlayer {
  id:        number;
  name:      string;
  team:      string;
  position:  string;
  xP:        number;
  buzz:      number;
  headline:  string | null;
}

export interface SquadWatchItem {
  name:     string;
  team:     string;
  buzz:     number;
  headline: string;
}

export interface BriefingResponse {
  date:               string;
  gameweek:           number;
  summary:            string;
  newsPills:          NewsPill[];
  deadlineTime:       string | null;
  communityHeadlines: CommunityHeadline[];
  hotPlayers:         HotPlayer[];
  squadWatch:         SquadWatchItem[];
}

export interface DataSource {
  name:       string;
  status:     "ok" | "warning";
  lastUpdate: string;
  count?:     number;
}

export interface StatusResponse {
  lastRefresh:         string | null;
  lastRefreshRelative: string;
  sources:             DataSource[];
}

export interface PoolPlayer {
  id:               number;
  name:             string;
  team:             string;
  teamCode?:        number;
  position:         Position;
  price:            number;
  xP:               number;
  form:             number;
  fitness:          FitnessStatus;
  selectedPct:      number;
  last5:            number[];
  costChangeEvent?:   number;
  costChangeStart?:   number;
  transfersInEvent?:  number;
  transfersOutEvent?: number;
}

export interface PlayersResponse {
  players: PoolPlayer[];
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} returned ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Endpoint functions
// ---------------------------------------------------------------------------

export const fetchSquad     = (gw?: number) =>
  fetchJSON<SquadResponse>(gw !== undefined ? `/squad?gw=${gw}` : "/squad");
export const fetchPlayers   = () => fetchJSON<PlayersResponse>("/players");
export const fetchRecommend = () => fetchJSON<{ recommendations: Recommendation[] }>("/recommend");
export const fetchBriefing  = () => fetchJSON<BriefingResponse>("/briefing");
export const fetchStatus    = () => fetchJSON<StatusResponse>("/status");
export const fetchHistory   = () => fetchJSON<HistoryResponse>("/history");
export const fetchStandings = () => fetchJSON<StandingsResponse>("/standings");
