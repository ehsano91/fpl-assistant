import { useState, useMemo } from "react";
import { useAppData } from "@/context/AppDataContext";
import type { Position, FitnessStatus, PoolPlayer, Player } from "@/lib/api";
import { Search, ArrowUpDown, Plus, X, BarChart3 } from "lucide-react";
import PlayerModal from "./PlayerModal";

type SortKey = "xP" | "price" | "form" | "selectedPct";

const positionBadgeColors: Record<Position, string> = {
  GK:  "bg-caution/20 text-caution",
  DEF: "bg-teal/20 text-teal",
  MID: "bg-primary/20 text-primary",
  FWD: "bg-danger/20 text-danger",
};

const fitnessColors: Record<FitnessStatus, string> = {
  fit:   "bg-primary",
  doubt: "bg-caution",
  out:   "bg-danger",
};

function MiniBar({ values, max }: { values: number[]; max: number }) {
  return (
    <div className="flex items-end gap-[2px] h-5">
      {values.map((v, i) => (
        <div key={i} className="w-[4px] rounded-t-sm bg-primary/60"
          style={{ height: `${(v / max) * 100}%` }}
        />
      ))}
    </div>
  );
}

export default function TransferPlannerTab() {
  const { playerPool } = useAppData();
  const [search,         setSearch]         = useState("");
  const [posFilter,      setPosFilter]      = useState<Position | "ALL">("ALL");
  const [sortKey,        setSortKey]        = useState<SortKey>("xP");
  const [sortAsc,        setSortAsc]        = useState(false);
  const [compareList,    setCompareList]    = useState<number[]>([]);
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);

  const toPlayer = (p: PoolPlayer): Player => ({
    id: p.id, name: p.name, shortName: p.name.split(" ").pop() || p.name,
    position: p.position, team: p.team, xP: p.xP,
    xPForecast: p.last5.length >= 6 ? p.last5.slice(0, 6) : [...p.last5, +(p.xP - 0.3).toFixed(1)],
    isCaptain: false, isViceCaptain: false, fitness: p.fitness,
  });

  const filtered = useMemo(() => {
    let list = playerPool;
    if (posFilter !== "ALL") list = list.filter((p) => p.position === posFilter);
    if (search) list = list.filter((p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.team.toLowerCase().includes(search.toLowerCase())
    );
    return [...list].sort((a, b) => sortAsc ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey]);
  }, [playerPool, search, posFilter, sortKey, sortAsc]);

  const compared  = playerPool.filter((p) => compareList.includes(p.id));
  const maxLast5  = 15;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const toggleCompare = (id: number) => {
    setCompareList((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 4 ? [...prev, id] : prev
    );
  };

  return (
    <div className="pb-4 px-4 space-y-4 max-w-3xl mx-auto">
      <h2 className="text-xl font-bold text-foreground">Transfer Planner</h2>

      <div className="flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search players or teams..."
            className="w-full bg-muted rounded-lg pl-9 pr-3 py-2 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>
        <div className="flex gap-1">
          {(["ALL", "GK", "DEF", "MID", "FWD"] as const).map((pos) => (
            <button key={pos} onClick={() => setPosFilter(pos)}
              className={`px-3 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${posFilter === pos ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}
            >
              {pos}
            </button>
          ))}
        </div>
      </div>

      {compared.length > 0 && (
        <div className="pill-card space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart3 size={16} className="text-primary" />
              <span className="text-sm font-bold text-foreground">Compare ({compared.length}/4)</span>
            </div>
            <button onClick={() => setCompareList([])} className="text-[10px] text-muted-foreground hover:text-foreground">Clear all</button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {compared.map((p) => (
              <div key={p.id} className="bg-muted rounded-lg p-2 relative">
                <button onClick={() => toggleCompare(p.id)} className="absolute top-1 right-1 text-muted-foreground hover:text-foreground">
                  <X size={12} />
                </button>
                <p className="text-xs font-bold text-foreground truncate pr-4">{p.name}</p>
                <p className="text-[10px] text-muted-foreground">{p.team} · £{p.price}m</p>
                <div className="flex items-center gap-3 mt-1.5">
                  <div>
                    <p className="text-[9px] text-muted-foreground">xP</p>
                    <p className="text-sm font-bold text-primary">{p.xP}</p>
                  </div>
                  <div>
                    <p className="text-[9px] text-muted-foreground">Form</p>
                    <p className="text-sm font-bold text-foreground">{p.form}</p>
                  </div>
                  <MiniBar values={p.last5} max={maxLast5} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-[1fr_60px_56px_52px_52px_36px] gap-1 px-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
        <span>Player</span>
        {([["xP", "xP"], ["price", "Price"], ["form", "Form"], ["selectedPct", "Sel%"]] as [SortKey, string][]).map(([key, label]) => (
          <button key={key} onClick={() => toggleSort(key)} className="flex items-center gap-0.5 justify-end hover:text-foreground transition-colors">
            {label}
            <ArrowUpDown size={10} className={sortKey === key ? "text-primary" : ""} />
          </button>
        ))}
        <span />
      </div>

      <div className="space-y-1">
        {filtered.map((p) => {
          const isCompared = compareList.includes(p.id);
          return (
            <div key={p.id}
              className={`grid grid-cols-[1fr_60px_56px_52px_52px_36px] gap-1 items-center pill-card py-2 ${isCompared ? "ring-1 ring-primary/50" : ""}`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 ${positionBadgeColors[p.position]}`}>
                  {p.position}
                </span>
                <div className="min-w-0 cursor-pointer" onClick={() => setSelectedPlayer(toPlayer(p))}>
                  <p className="text-xs font-semibold text-foreground truncate hover:text-primary transition-colors">{p.name}</p>
                  <p className="text-[10px] text-muted-foreground">{p.team}</p>
                </div>
                <span className={`w-2 h-2 rounded-full shrink-0 ${fitnessColors[p.fitness]}`} />
              </div>
              <p className="text-xs font-bold text-primary text-right">{p.xP}</p>
              <p className="text-xs font-semibold text-foreground text-right">£{p.price}m</p>
              <p className="text-xs text-foreground text-right">{p.form}</p>
              <p className="text-[10px] text-muted-foreground text-right">{p.selectedPct}%</p>
              <button onClick={() => toggleCompare(p.id)}
                className={`w-7 h-7 rounded-md flex items-center justify-center transition-colors ${isCompared ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}
              >
                {isCompared ? <X size={14} /> : <Plus size={14} />}
              </button>
            </div>
          );
        })}
      </div>

      {filtered.length === 0 && (
        <p className="text-center text-sm text-muted-foreground py-8">No players found</p>
      )}

      <PlayerModal player={selectedPlayer} open={!!selectedPlayer} onClose={() => setSelectedPlayer(null)} />
    </div>
  );
}
