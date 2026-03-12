import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchSquad, fetchPlayers, fetchRecommend, fetchBriefing, fetchStatus,
  fetchHistory, fetchStandings,
  Player, Recommendation, NewsPill, DataSource, PoolPlayer,
  GWHistory, League, CommunityHeadline, HotPlayer, SquadWatchItem, STALE_TIME,
} from "@/lib/api";

export interface PlanState {
  captainId:     number;
  viceCaptainId: number;
  starterIds:    number[];   // 11 player IDs in starter positions
}

interface AppData {
  myTeam:          Player[];
  bench:           Player[];
  gameweek:        number;
  recommendations: Recommendation[];
  briefingSummary:      string;
  newsPills:            NewsPill[];
  briefingDate:         string;
  deadlineTime:         string | null;
  communityHeadlines:   CommunityHeadline[];
  hotPlayers:           HotPlayer[];
  squadWatch:           SquadWatchItem[];
  dataSources:     DataSource[];
  lastRefresh:     string;
  playerPool:      PoolPlayer[];
  isLoading:       boolean;
  isError:         boolean;
  errorMsg:        string;
  // GW navigation
  selectedGW:      number | null;
  setSelectedGW:   (gw: number | null) => void;
  currentGW:       number;
  gwHistory:       GWHistory[];
  gwPoints:        number | null;
  // Rankings
  totalPoints:     number;
  overallRank:     number;
  swedenRank:      number | null;
  leagues:         League[];
  // Planning
  isPlanning:      boolean;
  planningState:   Record<number, PlanState>;
  setPlanForGW:    (gw: number, plan: PlanState) => void;
  resetPlanForGW:  (gw: number) => void;
}

const AppDataContext = createContext<AppData>({
  myTeam: [], bench: [], gameweek: 0,
  recommendations: [],
  briefingSummary: "", newsPills: [], briefingDate: "", deadlineTime: null,
  dataSources: [], lastRefresh: "",
  playerPool: [],
  isLoading: true, isError: false, errorMsg: "",
  selectedGW: null, setSelectedGW: () => {}, currentGW: 0,
  gwHistory: [], gwPoints: null,
  totalPoints: 0, overallRank: 0, swedenRank: null, leagues: [],
  isPlanning: false, planningState: {}, setPlanForGW: () => {}, resetPlanForGW: () => {},
  communityHeadlines: [], hotPlayers: [], squadWatch: [],
});

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [selectedGW, setSelectedGW] = useState<number | null>(null);

  const [planningState, setPlanningState] = useState<Record<number, PlanState>>(() => {
    try { return JSON.parse(localStorage.getItem("fpl-plans") ?? "{}"); }
    catch { return {}; }
  });

  useEffect(() => {
    localStorage.setItem("fpl-plans", JSON.stringify(planningState));
  }, [planningState]);

  const setPlanForGW = (gw: number, plan: PlanState) =>
    setPlanningState(prev => ({ ...prev, [gw]: plan }));

  const resetPlanForGW = (gw: number) =>
    setPlanningState(prev => { const n = { ...prev }; delete n[gw]; return n; });

  const squad     = useQuery({
    queryKey: ["squad", selectedGW],
    queryFn:  () => fetchSquad(selectedGW ?? undefined),
    staleTime: STALE_TIME,
  });
  const players   = useQuery({ queryKey: ["players"],   queryFn: fetchPlayers,   staleTime: STALE_TIME });
  const recommend = useQuery({ queryKey: ["recommend"], queryFn: fetchRecommend, staleTime: STALE_TIME });
  const briefing  = useQuery({ queryKey: ["briefing"],  queryFn: fetchBriefing,  staleTime: STALE_TIME });
  const status    = useQuery({ queryKey: ["status"],    queryFn: fetchStatus,    staleTime: STALE_TIME });
  const history   = useQuery({ queryKey: ["history"],   queryFn: fetchHistory,   staleTime: STALE_TIME });
  const standings = useQuery({ queryKey: ["standings"], queryFn: fetchStandings, staleTime: STALE_TIME });

  const isLoading = squad.isPending || recommend.isPending || briefing.isPending;
  const isError   = squad.isError   || recommend.isError   || briefing.isError;

  const value: AppData = {
    myTeam:          squad.data?.starters          ?? [],
    bench:           squad.data?.bench             ?? [],
    gameweek:        squad.data?.gameweek          ?? 0,
    recommendations: recommend.data?.recommendations ?? [],
    briefingSummary:    briefing.data?.summary            ?? "",
    newsPills:          briefing.data?.newsPills          ?? [],
    briefingDate:       briefing.data?.date               ?? "",
    deadlineTime:       briefing.data?.deadlineTime       ?? null,
    communityHeadlines: briefing.data?.communityHeadlines ?? [],
    hotPlayers:         briefing.data?.hotPlayers         ?? [],
    squadWatch:         briefing.data?.squadWatch         ?? [],
    dataSources:     status.data?.sources          ?? [],
    lastRefresh:     status.data?.lastRefreshRelative ?? "—",
    playerPool:      players.data?.players         ?? [],
    isLoading,
    isError,
    errorMsg: isError
      ? "Cannot connect to the FPL API server.\n\nMake sure it is running:\n  python3 engine/api_server.py"
      : "",
    // GW navigation
    selectedGW,
    setSelectedGW,
    currentGW:   history.data?.currentGW ?? squad.data?.gameweek ?? 0,
    gwHistory:   history.data?.history   ?? [],
    gwPoints:    squad.data?.points      ?? null,
    // Rankings
    totalPoints: standings.data?.totalPoints ?? 0,
    overallRank: standings.data?.overallRank ?? 0,
    swedenRank:  standings.data?.swedenRank  ?? null,
    leagues:     standings.data?.leagues     ?? [],
    // Planning
    isPlanning:    squad.data?.isPlanning  ?? false,
    planningState,
    setPlanForGW,
    resetPlanForGW,
  };

  return (
    <AppDataContext.Provider value={value}>
      {children}
    </AppDataContext.Provider>
  );
}

export function useAppData(): AppData {
  return useContext(AppDataContext);
}
