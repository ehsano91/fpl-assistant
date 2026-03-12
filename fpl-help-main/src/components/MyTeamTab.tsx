import { useState, useRef, useMemo } from "react";
import { useAppData } from "@/context/AppDataContext";
import type { PlanState } from "@/context/AppDataContext";
import type { Player } from "@/lib/api";
import PlayerModal from "./PlayerModal";

const teamColors: Record<string, { primary: string; secondary: string }> = {
  LIV: { primary: "#C8102E", secondary: "#C8102E" },
  ARS: { primary: "#EF0107", secondary: "#FFFFFF" },
  MCI: { primary: "#6CABDD", secondary: "#6CABDD" },
  CHE: { primary: "#034694", secondary: "#034694" },
  NEW: { primary: "#241F20", secondary: "#FFFFFF" },
  AVL: { primary: "#670E36", secondary: "#95BFE5" },
  TOT: { primary: "#FFFFFF", secondary: "#132257" },
  WHU: { primary: "#7A263A", secondary: "#1BB1E7" },
  BRE: { primary: "#E30613", secondary: "#FFFFFF" },
  FUL: { primary: "#000000", secondary: "#FFFFFF" },
};

function JerseySVG({ team, size }: { team: string; size: number }) {
  const colors = teamColors[team] || { primary: "#888", secondary: "#CCC" };
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className="drop-shadow-lg">
      <path d="M8 12 L0 24 L8 28 L12 18 Z" fill={colors.secondary} />
      <path d="M56 12 L64 24 L56 28 L52 18 Z" fill={colors.secondary} />
      <path d="M12 12 L12 56 Q12 60 16 60 L48 60 Q52 60 52 56 L52 12 L44 8 Q32 4 20 8 Z" fill={colors.primary} />
      <path d="M20 8 Q32 4 44 8 L40 14 Q32 10 24 14 Z" fill={colors.secondary} />
      <path d="M12 12 L20 8" stroke={colors.secondary} strokeWidth="1" />
      <path d="M52 12 L44 8" stroke={colors.secondary} strokeWidth="1" />
    </svg>
  );
}

const fitnessColors = { fit: "bg-primary", doubt: "bg-caution", out: "bg-danger" };

const fdrBg: Record<number, string> = {
  1: "bg-[#00FF85]/80",
  2: "bg-[#01c564]/70",
  3: "bg-[#BDB7B3]/60",
  4: "bg-[#FF7B52]/70",
  5: "bg-[#CC0000]/80",
};

function isValidFormation(starters: Player[]): boolean {
  const gk  = starters.filter(p => p.position === "GK").length;
  const def = starters.filter(p => p.position === "DEF").length;
  const mid = starters.filter(p => p.position === "MID").length;
  const fwd = starters.filter(p => p.position === "FWD").length;
  return gk === 1 && def >= 3 && def <= 5 && mid >= 2 && mid <= 5 && fwd >= 1 && fwd <= 3 && starters.length === 11;
}

function PlayerCard({
  player,
  onClick,
  isSelected,
  showCaptainMenu,
  onLongPress,
  onSetCaptain,
  onSetVC,
}: {
  player: Player;
  onClick: () => void;
  isSelected?: boolean;
  showCaptainMenu?: boolean;
  onLongPress?: () => void;
  onSetCaptain?: () => void;
  onSetVC?: () => void;
}) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handlePointerDown = () => {
    if (!onLongPress) return;
    timerRef.current = setTimeout(() => { onLongPress(); }, 350);
  };
  const handlePointerUp = () => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
  };

  return (
    <div className="relative flex flex-col items-center">
      {showCaptainMenu && (
        <div className="absolute -top-8 left-1/2 -translate-x-1/2 z-30 bg-card border border-border rounded-lg flex gap-0.5 p-0.5 shadow-xl">
          <button
            onClick={(e) => { e.stopPropagation(); onSetCaptain?.(); }}
            className="w-7 h-7 rounded-md bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center hover:opacity-80"
          >C</button>
          <button
            onClick={(e) => { e.stopPropagation(); onSetVC?.(); }}
            className="w-7 h-7 rounded-md bg-muted text-foreground text-[10px] font-bold flex items-center justify-center hover:bg-secondary"
          >V</button>
        </div>
      )}
      <button
        onClick={onClick}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        className={`relative flex flex-col items-center cursor-pointer hover:scale-105 transition-transform group w-[80px] md:w-[100px] ${isSelected ? "scale-105 drop-shadow-[0_0_6px_hsl(45,100%,60%)]" : ""}`}
      >
        <div className="relative">
          <JerseySVG team={player.team} size={48} />
          {isSelected && (
            <div className="absolute inset-0 rounded-full ring-2 ring-caution ring-offset-1 ring-offset-transparent pointer-events-none" />
          )}
          {player.isCaptain && (
            <span className="absolute -top-1 -right-1 w-5 h-5 md:w-6 md:h-6 rounded-full bg-primary text-primary-foreground text-[10px] md:text-[11px] font-bold flex items-center justify-center shadow-md border-2 border-background">C</span>
          )}
          {player.isViceCaptain && (
            <span className="absolute -top-1 -right-1 w-5 h-5 md:w-6 md:h-6 rounded-full bg-muted text-foreground text-[10px] md:text-[11px] font-bold flex items-center justify-center shadow-md border-2 border-background">V</span>
          )}
          <span className={`absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full ${fitnessColors[player.fitness]} border border-background`} />
        </div>
        <div className="bg-card/90 backdrop-blur-sm rounded-md px-2 py-0.5 mt-1 w-full text-center shadow-md">
          <p className="text-[11px] md:text-xs font-semibold text-foreground truncate">{player.shortName}</p>
        </div>
        <div className="bg-primary/20 rounded-md px-2 py-0.5 mt-0.5 w-full text-center">
          <p className="text-[10px] md:text-[11px] font-bold text-primary">{player.xP} xP</p>
        </div>
        {player.opponent && (
          <div className={`rounded-md px-1.5 py-0.5 mt-0.5 w-full text-center ${fdrBg[player.fdr ?? 3]}`}>
            <p className="text-[9px] font-semibold text-white">{player.isHome ? "vs" : "@"} {player.opponent}</p>
          </div>
        )}
      </button>
    </div>
  );
}

export default function MyTeamTab() {
  const {
    myTeam, bench, gameweek,
    selectedGW, currentGW, gwPoints,
    totalPoints, overallRank, swedenRank, leagues,
    isPlanning, planningState, setPlanForGW, resetPlanForGW,
  } = useAppData();

  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);
  const [swapSource, setSwapSource]         = useState<number | null>(null);
  const [captainMenu, setCaptainMenu]       = useState<number | null>(null);
  const [swapError, setSwapError]           = useState(false);

  const displayGW    = selectedGW ?? currentGW ?? gameweek;
  const isHistorical = selectedGW !== null && !isPlanning;

  const allPlayers = useMemo(() => [...myTeam, ...bench], [myTeam, bench]);

  const getDefaultPlan = (): PlanState => ({
    captainId:     myTeam.find(p => p.isCaptain)?.id     ?? myTeam[0]?.id ?? 0,
    viceCaptainId: myTeam.find(p => p.isViceCaptain)?.id ?? myTeam[1]?.id ?? 0,
    starterIds:    myTeam.map(p => p.id),
  });

  const activePlan = isPlanning ? (planningState[displayGW] ?? null) : null;

  const { displayedStarters, displayedBench } = useMemo(() => {
    if (!isPlanning || !activePlan) {
      return { displayedStarters: myTeam, displayedBench: bench };
    }
    const withCaptain = allPlayers.map(p => ({
      ...p,
      isCaptain:     p.id === activePlan.captainId,
      isViceCaptain: p.id === activePlan.viceCaptainId,
    }));
    return {
      displayedStarters: withCaptain.filter(p => activePlan.starterIds.includes(p.id)),
      displayedBench:    withCaptain.filter(p => !activePlan.starterIds.includes(p.id)),
    };
  }, [isPlanning, activePlan, allPlayers, myTeam, bench]);

  const gk  = displayedStarters.filter(p => p.position === "GK");
  const def = displayedStarters.filter(p => p.position === "DEF");
  const mid = displayedStarters.filter(p => p.position === "MID");
  const fwd = displayedStarters.filter(p => p.position === "FWD");
  const rows = [gk, def, mid, fwd];

  const formationStr = `${def.length}-${mid.length}-${fwd.length}`;

  const executeSwap = (id1: number, id2: number) => {
    const base = activePlan ?? getDefaultPlan();
    const id1IsStarter = base.starterIds.includes(id1);
    const id2IsStarter = base.starterIds.includes(id2);

    const newStarters = [...base.starterIds];

    if (id1IsStarter === id2IsStarter) {
      // Swap within the same group (reorder only — no formation change)
      const i1 = newStarters.indexOf(id1);
      const i2 = newStarters.indexOf(id2);
      if (i1 !== -1 && i2 !== -1) [newStarters[i1], newStarters[i2]] = [newStarters[i2], newStarters[i1]];
      setPlanForGW(displayGW, { ...base, starterIds: newStarters });
      return;
    }

    // One starter ↔ one bench player
    const starterId = id1IsStarter ? id1 : id2;
    const benchId   = id1IsStarter ? id2 : id1;
    const idx = newStarters.indexOf(starterId);
    newStarters[idx] = benchId;

    const proposed = allPlayers.filter(p => newStarters.includes(p.id));
    if (!isValidFormation(proposed)) {
      setSwapError(true);
      setTimeout(() => setSwapError(false), 1800);
      return;
    }
    setPlanForGW(displayGW, { ...base, starterIds: newStarters });
  };

  const handlePlayerClick = (player: Player) => {
    if (!isPlanning) { setSelectedPlayer(player); return; }
    if (captainMenu !== null) { setCaptainMenu(null); return; }
    if (swapSource === null) {
      setSwapSource(player.id);
    } else if (swapSource === player.id) {
      setSwapSource(null);
    } else {
      executeSwap(swapSource, player.id);
      setSwapSource(null);
    }
  };

  const handleLongPress = (playerId: number) => {
    if (!isPlanning) return;
    setSwapSource(null);
    setCaptainMenu(playerId === captainMenu ? null : playerId);
  };

  const handleSetCaptain = (playerId: number) => {
    const base = activePlan ?? getDefaultPlan();
    setPlanForGW(displayGW, { ...base, captainId: playerId });
    setCaptainMenu(null);
  };

  const handleSetVC = (playerId: number) => {
    const base = activePlan ?? getDefaultPlan();
    setPlanForGW(displayGW, { ...base, viceCaptainId: playerId });
    setCaptainMenu(null);
  };

  return (
    <div className="pb-4 px-4" onClick={() => { if (captainMenu !== null) setCaptainMenu(null); }}>
      <h2 className="text-xl font-bold text-foreground mb-4 flex items-center gap-2 flex-wrap">
        My Team — {displayGW ? `GW${displayGW}` : "—"}
        {isHistorical && gwPoints !== null && (
          <span className="text-sm font-semibold bg-primary/20 text-primary rounded-full px-2 py-0.5">
            {gwPoints} pts
          </span>
        )}
        {isPlanning && (
          <span className="text-sm font-semibold bg-caution/20 text-caution rounded-full px-2 py-0.5">
            {formationStr} · Plan
          </span>
        )}
      </h2>

      {isPlanning && (
        <p className="text-[11px] text-muted-foreground mb-3 text-center">
          Tap a player to swap · Long-press for captain / VC
        </p>
      )}

      {swapError && (
        <div className="text-center text-xs text-danger font-semibold mb-2 animate-pulse">
          Invalid formation — swap not allowed
        </div>
      )}

      <div className="rounded-2xl overflow-hidden relative max-w-2xl mx-auto"
        style={{
          background: "linear-gradient(180deg, hsl(142 60% 32%) 0%, hsl(142 55% 38%) 30%, hsl(142 50% 35%) 60%, hsl(142 60% 30%) 100%)"
        }}
      >
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="absolute top-1/2 left-6 right-6 border-t-2 border-foreground/10" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-28 h-28 md:w-36 md:h-36 border-2 border-foreground/10 rounded-full" />
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-40 md:w-52 h-14 md:h-20 border-b-2 border-l-2 border-r-2 border-foreground/10" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-40 md:w-52 h-14 md:h-20 border-t-2 border-l-2 border-r-2 border-foreground/10" />
          <div className="absolute inset-0 flex flex-col">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="flex-1"
                style={{ background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.03)" }}
              />
            ))}
          </div>
        </div>

        <div className="relative z-10 flex flex-col gap-6 md:gap-10 py-8 md:py-14 px-4">
          {rows.map((row, i) => (
            <div key={i} className="flex justify-center gap-4 md:gap-8">
              {row.map((p) => (
                <PlayerCard
                  key={p.id}
                  player={p}
                  onClick={() => handlePlayerClick(p)}
                  isSelected={isPlanning && swapSource === p.id}
                  showCaptainMenu={isPlanning && captainMenu === p.id}
                  onLongPress={isPlanning ? () => handleLongPress(p.id) : undefined}
                  onSetCaptain={() => handleSetCaptain(p.id)}
                  onSetVC={() => handleSetVC(p.id)}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="max-w-2xl mx-auto mt-4">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Substitutes</h3>
        <div className="flex justify-center gap-4 md:gap-8">
          {displayedBench.map((p) => (
            <PlayerCard
              key={p.id}
              player={p}
              onClick={() => handlePlayerClick(p)}
              isSelected={isPlanning && swapSource === p.id}
              showCaptainMenu={isPlanning && captainMenu === p.id}
              onLongPress={isPlanning ? () => handleLongPress(p.id) : undefined}
              onSetCaptain={() => handleSetCaptain(p.id)}
              onSetVC={() => handleSetVC(p.id)}
            />
          ))}
        </div>
      </div>

      {isPlanning && (
        <div className="max-w-2xl mx-auto mt-4 text-center">
          <button
            onClick={() => resetPlanForGW(displayGW)}
            className="text-xs text-muted-foreground underline hover:text-foreground transition-colors"
          >
            Reset to actual squad
          </button>
        </div>
      )}

      <div className="max-w-2xl mx-auto mt-6">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">My Rankings</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <div className="pill-card text-center">
            <p className="text-[9px] text-muted-foreground uppercase">Overall</p>
            <p className="text-sm font-bold text-foreground">
              {overallRank > 0 ? overallRank.toLocaleString() : "—"}
            </p>
          </div>
          {swedenRank && (
            <div className="pill-card text-center">
              <p className="text-[9px] text-muted-foreground uppercase">Sweden</p>
              <p className="text-sm font-bold text-foreground">{swedenRank.toLocaleString()}</p>
            </div>
          )}
          {leagues.map((l) => (
            <div key={l.id} className="pill-card text-center">
              <p className="text-[9px] text-muted-foreground uppercase truncate">{l.name}</p>
              <p className="text-sm font-bold text-foreground">#{l.rank}</p>
              <p className="text-[9px] text-muted-foreground">
                {l.rank < l.lastRank ? "↑" : l.rank > l.lastRank ? "↓" : "="} last: #{l.lastRank}
              </p>
            </div>
          ))}
        </div>
      </div>

      <PlayerModal player={selectedPlayer} open={!!selectedPlayer} onClose={() => setSelectedPlayer(null)} />
    </div>
  );
}
