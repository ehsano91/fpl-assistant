import { useState, useRef, useMemo } from "react";
import { useAppData } from "@/context/AppDataContext";
import type { PlanState } from "@/context/AppDataContext";
import type { Player, PoolPlayer, Position } from "@/lib/api";
import PlayerModal from "./PlayerModal";

// ---------------------------------------------------------------------------
// Jersey image using the official FPL CDN
// ---------------------------------------------------------------------------

function JerseyImg({ teamCode, position, size }: { teamCode?: number; position?: string; size: number }) {
  const [errored, setErrored] = useState(false);
  if (!teamCode || errored) {
    // Fallback: coloured circle with position label
    const bg = position === "GK" ? "#f5a623" : position === "DEF" ? "#4a90d9" : position === "MID" ? "#7ed321" : "#d0021b";
    return (
      <div
        style={{ width: size, height: size, background: bg }}
        className="rounded-full flex items-center justify-center text-white font-bold drop-shadow-lg"
        aria-hidden
      >
        <span style={{ fontSize: Math.max(8, size / 4) }}>{position ?? "?"}</span>
      </div>
    );
  }
  const isGK = position === "GK";
  const src = isGK
    ? `https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${teamCode}_1-66.png`
    : `https://fantasy.premierleague.com/dist/img/shirts/standard/shirt_${teamCode}-66.png`;
  return (
    <img
      src={src}
      width={size}
      height={size}
      alt=""
      className="drop-shadow-lg"
      onError={() => setErrored(true)}
    />
  );
}

// ---------------------------------------------------------------------------
// Price change arrow
// ---------------------------------------------------------------------------

function PriceChange({ delta, onClick }: { delta: number; onClick?: () => void }) {
  if (!delta) return null;
  const rise = delta > 0;
  const cls = `text-[9px] font-bold leading-none ${rise ? "text-emerald-400" : "text-rose-400"}`;
  if (onClick) {
    return (
      <button
        className={`${cls} underline-offset-2 hover:underline focus:outline-none`}
        onClick={(e) => { e.stopPropagation(); onClick(); }}
        aria-label="Price change details"
      >
        {rise ? "▲" : "▼"} £{(Math.abs(delta) / 10).toFixed(1)}m
      </button>
    );
  }
  return (
    <span className={cls}>
      {rise ? "▲" : "▼"} £{(Math.abs(delta) / 10).toFixed(1)}m
    </span>
  );
}

// ---------------------------------------------------------------------------
// Transfer modal (bottom sheet)
// ---------------------------------------------------------------------------

function TransferModal({
  outPlayer,
  playerPool,
  squadIds,
  squadPlayers,
  onSelect,
  onClose,
}: {
  outPlayer: Player;
  playerPool: PoolPlayer[];
  squadIds: number[];
  squadPlayers: Player[];
  onSelect: (p: PoolPlayer) => void;
  onClose: () => void;
}) {
  // Count team members in effective squad, excluding the outgoing player's slot
  const teamCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of squadPlayers) {
      if (p.id === outPlayer.id) continue;
      counts[p.team] = (counts[p.team] ?? 0) + 1;
    }
    return counts;
  }, [squadPlayers, outPlayer.id]);

  const filtered = playerPool
    .filter(p =>
      p.position === outPlayer.position &&
      !squadIds.includes(p.id) &&
      (teamCounts[p.team] ?? 0) < 3
    )
    .sort((a, b) => b.xP - a.xP);

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end bg-black/50" onClick={onClose}>
      <div
        className="bg-card rounded-t-2xl max-h-[70vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-border">
          <div>
            <h3 className="font-bold text-sm">Transfer out: {outPlayer.shortName}</h3>
            <p className="text-[11px] text-muted-foreground">Select a {outPlayer.position} to bring in</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">✕</button>
        </div>
        <div className="overflow-y-auto flex-1 px-3 py-2 space-y-1">
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-6">No players available</p>
          )}
          {filtered.map(p => {
            const count = teamCounts[p.team] ?? 0;
            return (
              <button
                key={p.id}
                onClick={() => { onSelect(p); onClose(); }}
                className="w-full flex items-center gap-3 p-2 rounded-xl hover:bg-muted/50 active:bg-muted transition-colors"
              >
                <JerseyImg teamCode={p.teamCode} position={p.position} size={36} />
                <div className="flex-1 text-left min-w-0">
                  <p className="text-sm font-semibold truncate">{p.name}</p>
                  <div className="flex items-center gap-1.5">
                    <p className="text-[11px] text-muted-foreground">{p.team}</p>
                    {count >= 2 && (
                      <span className="text-[10px] text-muted-foreground/60">{count}/3</span>
                    )}
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-xs font-semibold">£{p.price}m</p>
                  <p className="text-xs text-primary font-bold">{p.xP} xP</p>
                  <PriceChange delta={p.costChangeEvent ?? 0} />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function poolPlayerToPlayer(pp: PoolPlayer): Player {
  return {
    id:               pp.id,
    name:             pp.name,
    shortName:        pp.name,
    position:         pp.position,
    team:             pp.team,
    teamCode:         pp.teamCode,
    xP:               pp.xP,
    xPForecast:       pp.last5,
    isCaptain:        false,
    isViceCaptain:    false,
    fitness:          pp.fitness,
    opponent:         null,
    isHome:           null,
    fdr:              null,
    price:            pp.price,
    costChangeEvent:  pp.costChangeEvent,
    costChangeStart:  pp.costChangeStart,
    transfersInEvent: pp.transfersInEvent,
    transfersOutEvent: pp.transfersOutEvent,
  };
}

// ---------------------------------------------------------------------------
// PlayerCard
// ---------------------------------------------------------------------------

function PlayerCard({
  player,
  onClick,
  isSelected,
  isTransferred,
  showCaptainMenu,
  onLongPress,
  onSetCaptain,
  onSetVC,
  onTransfer,
  isPlanning,
  onPriceClick,
}: {
  player: Player;
  onClick: () => void;
  isSelected?: boolean;
  isTransferred?: boolean;
  showCaptainMenu?: boolean;
  onLongPress?: () => void;
  onSetCaptain?: () => void;
  onSetVC?: () => void;
  onTransfer?: () => void;
  isPlanning?: boolean;
  onPriceClick?: (player: Player) => void;
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
          <JerseyImg teamCode={player.teamCode} position={player.position} size={48} />
          {isSelected && (
            <div className="absolute inset-0 rounded-full ring-2 ring-caution ring-offset-1 ring-offset-transparent pointer-events-none" />
          )}
          {player.isCaptain && (
            <span className="absolute -top-1 -right-1 w-5 h-5 md:w-6 md:h-6 rounded-full bg-primary text-primary-foreground text-[10px] md:text-[11px] font-bold flex items-center justify-center shadow-md border-2 border-background">C</span>
          )}
          {player.isViceCaptain && (
            <span className="absolute -top-1 -right-1 w-5 h-5 md:w-6 md:h-6 rounded-full bg-muted text-foreground text-[10px] md:text-[11px] font-bold flex items-center justify-center shadow-md border-2 border-background">V</span>
          )}
          {isTransferred && (
            <span className="absolute -top-1 -left-1 w-5 h-5 rounded-full bg-violet-500 text-white text-[9px] font-bold flex items-center justify-center shadow-md border-2 border-background">↕</span>
          )}
          {/* Transfer button — only in planning mode */}
          {isPlanning && onTransfer && (
            <button
              onClick={(e) => { e.stopPropagation(); onTransfer(); }}
              className="absolute -bottom-1 -left-1 w-5 h-5 rounded-full bg-card/90 border border-border text-[10px] flex items-center justify-center hover:bg-violet-500 hover:text-white hover:border-violet-500 transition-colors z-20 shadow"
              title="Transfer"
            >↕</button>
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
        {(player.costChangeEvent ?? 0) !== 0 && (
          <div className="mt-0.5 w-full text-center">
            <PriceChange delta={player.costChangeEvent ?? 0} onClick={onPriceClick ? () => onPriceClick(player) : undefined} />
          </div>
        )}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MyTeamTab
// ---------------------------------------------------------------------------

export default function MyTeamTab() {
  const {
    myTeam, bench, gameweek, squadValue,
    selectedGW, currentGW, gwPoints,
    totalPoints, overallRank, swedenRank, leagues,
    isPlanning, planningState, setPlanForGW, resetPlanForGW,
    playerPool, itb,
  } = useAppData();

  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);
  const [swapSource, setSwapSource]         = useState<number | null>(null);
  const [captainMenu, setCaptainMenu]       = useState<number | null>(null);
  const [swapError, setSwapError]           = useState(false);
  const [transferModal, setTransferModal]   = useState<Player | null>(null);
  const [pricePopover, setPricePopover]     = useState<Player | null>(null);
  const [saveErrors, setSaveErrors]         = useState<string[]>([]);
  const [savedGW, setSavedGW]               = useState<number | null>(null);

  const displayGW    = selectedGW ?? currentGW ?? gameweek;
  const isHistorical = selectedGW !== null && !isPlanning;

  const allPlayers = useMemo(() => [...myTeam, ...bench], [myTeam, bench]);

  const getDefaultPlan = (): PlanState => ({
    captainId:     myTeam.find(p => p.isCaptain)?.id     ?? myTeam[0]?.id ?? 0,
    viceCaptainId: myTeam.find(p => p.isViceCaptain)?.id ?? myTeam[1]?.id ?? 0,
    starterIds:    myTeam.map(p => p.id),
    transfers:     [],
  });

  const activePlan = isPlanning ? (planningState[displayGW] ?? null) : null;

  // Apply transfers to get the effective 15-player list
  // Uses stored inPlayer first (fixes GK bug), falls back to playerPool lookup for legacy plans
  const effectivePlayers = useMemo(() => {
    if (!isPlanning || !activePlan) return allPlayers;
    const transfers = activePlan.transfers ?? [];
    return allPlayers.map(p => {
      const tx = transfers.find(t => t.out === p.id);
      if (tx) {
        const incoming = tx.inPlayer ?? playerPool.find(pp => pp.id === tx.in);
        if (incoming) return poolPlayerToPlayer(incoming);
      }
      return p;
    });
  }, [isPlanning, activePlan, allPlayers, playerPool]);

  const transferredInIds = useMemo(() => {
    if (!activePlan) return new Set<number>();
    return new Set((activePlan.transfers ?? []).map(t => t.in));
  }, [activePlan]);

  const { displayedStarters, displayedBench } = useMemo(() => {
    if (!isPlanning || !activePlan) {
      return { displayedStarters: myTeam, displayedBench: bench };
    }
    const withCaptain = effectivePlayers.map(p => ({
      ...p,
      isCaptain:     p.id === activePlan.captainId,
      isViceCaptain: p.id === activePlan.viceCaptainId,
    }));
    return {
      displayedStarters: withCaptain.filter(p => activePlan.starterIds.includes(p.id)),
      displayedBench:    withCaptain.filter(p => !activePlan.starterIds.includes(p.id)),
    };
  }, [isPlanning, activePlan, effectivePlayers, myTeam, bench]);

  const gk  = displayedStarters.filter(p => p.position === "GK");
  const def = displayedStarters.filter(p => p.position === "DEF");
  const mid = displayedStarters.filter(p => p.position === "MID");
  const fwd = displayedStarters.filter(p => p.position === "FWD");
  const rows = [gk, def, mid, fwd];

  const formationStr = `${def.length}-${mid.length}-${fwd.length}`;

  // Club violation: any team has > 3 players in the effective squad
  const clubViolationTeam = useMemo(() => {
    if (!isPlanning || !activePlan) return null;
    const counts: Record<string, number> = {};
    for (const p of effectivePlayers) {
      counts[p.team] = (counts[p.team] ?? 0) + 1;
    }
    return Object.entries(counts).find(([, n]) => n > 3)?.[0] ?? null;
  }, [isPlanning, activePlan, effectivePlayers]);

  // Budget: net cost of all planned transfers vs ITB
  const netTransferCost = useMemo(() => {
    if (!activePlan) return 0;
    return (activePlan.transfers ?? []).reduce((sum, tx) => {
      const outP     = allPlayers.find(p => p.id === tx.out);
      const inPrice  = tx.inPlayer?.price ?? playerPool.find(pp => pp.id === tx.in)?.price ?? 0;
      const outPrice = outP?.price ?? 0;
      return sum + (inPrice - outPrice);
    }, 0);
  }, [activePlan, allPlayers, playerPool]);

  const executeSwap = (id1: number, id2: number) => {
    const base = activePlan ?? getDefaultPlan();
    const id1IsStarter = base.starterIds.includes(id1);
    const id2IsStarter = base.starterIds.includes(id2);

    const newStarters = [...base.starterIds];

    if (id1IsStarter === id2IsStarter) {
      const i1 = newStarters.indexOf(id1);
      const i2 = newStarters.indexOf(id2);
      if (i1 !== -1 && i2 !== -1) [newStarters[i1], newStarters[i2]] = [newStarters[i2], newStarters[i1]];
      setPlanForGW(displayGW, { ...base, starterIds: newStarters });
      return;
    }

    const starterId = id1IsStarter ? id1 : id2;
    const benchId   = id1IsStarter ? id2 : id1;
    const idx = newStarters.indexOf(starterId);
    newStarters[idx] = benchId;

    const proposed = effectivePlayers.filter(p => newStarters.includes(p.id));
    if (!isValidFormation(proposed)) {
      setSwapError(true);
      setTimeout(() => setSwapError(false), 1800);
      return;
    }
    setPlanForGW(displayGW, { ...base, starterIds: newStarters });
  };

  const executeTransfer = (outPlayer: Player, incoming: PoolPlayer) => {
    const base = activePlan ?? getDefaultPlan();
    const existingTransfers = base.transfers ?? [];

    // Remove any previous transfer involving the same out or in player
    const newTransfers = [
      ...existingTransfers.filter(t => t.out !== outPlayer.id && t.in !== incoming.id),
      { out: outPlayer.id, in: incoming.id, inPlayer: incoming },
    ];

    // If outgoing player was in starterIds, replace with incoming
    const newStarters = base.starterIds.map(id => id === outPlayer.id ? incoming.id : id);

    // Update captain/VC if they were the outgoing player
    const newCaptainId    = base.captainId    === outPlayer.id ? incoming.id : base.captainId;
    const newVCId         = base.viceCaptainId === outPlayer.id ? incoming.id : base.viceCaptainId;

    setPlanForGW(displayGW, {
      ...base,
      transfers:     newTransfers,
      starterIds:    newStarters,
      captainId:     newCaptainId,
      viceCaptainId: newVCId,
    });
  };

  const handleSavePlan = () => {
    const errors: string[] = [];
    if (clubViolationTeam) {
      errors.push(`More than 3 players from ${clubViolationTeam} — FPL allows a maximum of 3 per club.`);
    }
    if (itb > 0 && netTransferCost > itb) {
      errors.push(`Net transfer cost £${netTransferCost.toFixed(1)}m exceeds your ITB of £${itb.toFixed(1)}m.`);
    }
    if (errors.length > 0) {
      setSaveErrors(errors);
    } else {
      // Plan is already persisted via the useEffect in AppDataContext; just confirm
      setSavedGW(displayGW);
      setTimeout(() => setSavedGW(null), 2500);
    }
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

  // IDs currently in the effective squad (to exclude from transfer modal)
  const effectiveSquadIds = effectivePlayers.map(p => p.id);

  return (
    <div className="pb-4 px-4" onClick={() => { if (captainMenu !== null) setCaptainMenu(null); }}>
      <h2 className="text-xl font-bold text-foreground mb-1 flex items-center gap-2 flex-wrap">
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

      {/* Squad value */}
      {squadValue > 0 && (
        <p className="text-xs text-muted-foreground mb-3">
          Squad Value <span className="font-semibold text-foreground">£{squadValue.toFixed(1)}m</span>
          {itb > 0 && (
            <> · ITB <span className="font-semibold text-foreground">£{itb.toFixed(1)}m</span></>
          )}
        </p>
      )}

      {isPlanning && (
        <p className="text-[11px] text-muted-foreground mb-3 text-center">
          Tap to swap · Long-press for C/VC · ↕ to transfer
        </p>
      )}

      {swapError && (
        <div className="text-center text-xs text-danger font-semibold mb-2 animate-pulse">
          Invalid formation — swap not allowed
        </div>
      )}

      {/* Inline validation alerts */}
      {isPlanning && activePlan && clubViolationTeam && (
        <div className="max-w-2xl mx-auto mb-3 px-3 py-2 rounded-xl bg-danger/15 border border-danger/40 text-danger text-xs font-semibold">
          ⚠ More than 3 players from {clubViolationTeam} — FPL rule violation
        </div>
      )}
      {isPlanning && activePlan && itb > 0 && netTransferCost > itb && (
        <div className="max-w-2xl mx-auto mb-3 px-3 py-2 rounded-xl bg-danger/15 border border-danger/40 text-danger text-xs font-semibold">
          ⚠ Transfer cost £{netTransferCost.toFixed(1)}m exceeds ITB £{itb.toFixed(1)}m
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
                  isTransferred={transferredInIds.has(p.id)}
                  showCaptainMenu={isPlanning && captainMenu === p.id}
                  onLongPress={isPlanning ? () => handleLongPress(p.id) : undefined}
                  onSetCaptain={() => handleSetCaptain(p.id)}
                  onSetVC={() => handleSetVC(p.id)}
                  onTransfer={isPlanning ? () => setTransferModal(p) : undefined}
                  isPlanning={isPlanning}
                  onPriceClick={setPricePopover}
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
              isTransferred={transferredInIds.has(p.id)}
              showCaptainMenu={isPlanning && captainMenu === p.id}
              onLongPress={isPlanning ? () => handleLongPress(p.id) : undefined}
              onSetCaptain={() => handleSetCaptain(p.id)}
              onSetVC={() => handleSetVC(p.id)}
              onTransfer={isPlanning ? () => setTransferModal(p) : undefined}
              isPlanning={isPlanning}
              onPriceClick={setPricePopover}
            />
          ))}
        </div>
      </div>

      {isPlanning && (
        <div className="max-w-2xl mx-auto mt-4 flex items-center justify-between">
          <button
            onClick={() => resetPlanForGW(displayGW)}
            className="text-xs text-muted-foreground underline hover:text-foreground transition-colors"
          >
            Reset
          </button>
          <button
            onClick={handleSavePlan}
            className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-semibold shadow"
          >
            Save GW{displayGW} Plan
          </button>
        </div>
      )}

      {/* Saved toast */}
      {savedGW !== null && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 bg-primary text-primary-foreground text-sm font-semibold px-5 py-2.5 rounded-full shadow-xl">
          GW{savedGW} plan saved
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

      {pricePopover && (() => {
        const p = pricePopover;
        const rise = (p.costChangeEvent ?? 0) > 0;
        const inEv  = p.transfersInEvent  ?? 0;
        const outEv = p.transfersOutEvent ?? 0;
        const net   = inEv - outEv;
        const summary =
          net >  50000 ? "Heavily transferred in this GW" :
          net >  10000 ? "Net transfer in this GW" :
          net < -50000 ? "Mass exodus this GW" :
          net < -10000 ? "Net transfer out this GW" :
          Math.abs(net) <= 10000 && outEv > 0 ? "Slight movement this GW" :
          "Price change this GW";
        return (
          <div
            className="fixed inset-0 z-50"
            onClick={() => setPricePopover(null)}
          >
            <div
              className="absolute bottom-20 left-1/2 -translate-x-1/2 w-72 bg-card border border-border rounded-2xl shadow-2xl p-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-sm font-bold text-foreground">{p.shortName}</p>
                  <p className="text-[10px] text-muted-foreground">{p.position} · {p.team}</p>
                </div>
                <button
                  className="text-muted-foreground hover:text-foreground text-lg leading-none"
                  onClick={() => setPricePopover(null)}
                >✕</button>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Price change this GW</span>
                  <span className={`font-bold ${rise ? "text-emerald-400" : "text-rose-400"}`}>
                    {rise ? "▲" : "▼"} £{(Math.abs(p.costChangeEvent ?? 0) / 10).toFixed(1)}m
                  </span>
                </div>
                {(p.costChangeStart ?? 0) !== 0 && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Since season start</span>
                    <span className={`font-bold ${(p.costChangeStart ?? 0) > 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {(p.costChangeStart ?? 0) > 0 ? "▲" : "▼"} £{(Math.abs(p.costChangeStart ?? 0) / 10).toFixed(1)}m
                    </span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Transferred in this GW</span>
                  <span className="font-semibold text-emerald-400">{inEv.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Transferred out this GW</span>
                  <span className="font-semibold text-rose-400">{outEv.toLocaleString()}</span>
                </div>
              </div>
              <p className="mt-3 text-[11px] text-muted-foreground italic border-t border-border pt-2">{summary}</p>
            </div>
          </div>
        );
      })()}

      {transferModal && (
        <TransferModal
          outPlayer={transferModal}
          playerPool={playerPool}
          squadIds={effectiveSquadIds}
          squadPlayers={effectivePlayers}
          onSelect={(incoming) => executeTransfer(transferModal, incoming)}
          onClose={() => setTransferModal(null)}
        />
      )}

      {/* Save errors modal */}
      {saveErrors.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-card border border-border rounded-2xl p-5 mx-4 max-w-sm w-full shadow-2xl">
            <h3 className="font-bold text-sm mb-3 text-danger">Plan cannot be saved</h3>
            <ul className="space-y-2 text-xs text-foreground">
              {saveErrors.map((e, i) => (
                <li key={i} className="flex gap-2"><span>⚠</span>{e}</li>
              ))}
            </ul>
            <button
              onClick={() => setSaveErrors([])}
              className="mt-4 w-full py-2 rounded-xl bg-primary text-primary-foreground text-sm font-semibold"
            >
              Fix Plan
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
