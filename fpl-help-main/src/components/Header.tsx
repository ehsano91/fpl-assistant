import { ChevronLeft, ChevronRight, Trophy, TrendingUp, Award } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAppData } from "@/context/AppDataContext";

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border rounded-lg px-2 py-1 shadow-lg">
      <p className="text-[10px] text-muted-foreground">GW {payload[0].payload.gw}</p>
      <p className="text-xs font-bold text-primary">{payload[0].value} pts</p>
    </div>
  );
};

export default function Header() {
  const { gwHistory, totalPoints, overallRank, selectedGW, setSelectedGW, currentGW } = useAppData();

  const displayGW = selectedGW ?? currentGW;

  // Sparkline data shape: { gw, pts }
  const sparkData = gwHistory.map((h) => ({ gw: h.gw, pts: h.points }));

  const goBack = () => {
    const prev = Math.max(1, displayGW - 1);
    setSelectedGW(prev === currentGW ? null : prev);
  };
  const goForward = () => {
    if (displayGW >= 38) return;
    const next = displayGW + 1;
    setSelectedGW(next === currentGW ? null : next);
  };

  const atFirst   = displayGW <= 1;
  const atCurrent = selectedGW === null;
  const atFuture  = selectedGW !== null && currentGW > 0 && selectedGW > currentGW;

  return (
    <header className="bg-card border-b border-border sticky top-0 z-40">
      <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
        {/* Branding */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <Award size={18} className="text-primary-foreground" />
          </div>
          <div className="hidden sm:block">
            <p className="text-sm font-bold text-foreground leading-none">FPL</p>
            <p className="text-[10px] text-muted-foreground leading-none mt-0.5">Assistant</p>
          </div>
        </div>

        {/* Mini sparkline chart */}
        <div className="hidden md:block w-[200px] h-[40px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
              <defs>
                <linearGradient id="pointsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(153, 100%, 50%)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="hsl(153, 100%, 50%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="gw" hide />
              <YAxis hide domain={["dataMin - 10", "dataMax + 10"]} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="pts"
                stroke="hsl(153, 100%, 50%)"
                strokeWidth={1.5}
                fill="url(#pointsGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Gameweek selector */}
        <div className="flex items-center gap-1 bg-muted rounded-lg px-1 py-1">
          <button
            onClick={goBack}
            disabled={atFirst}
            className="p-1 rounded-md hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="text-xs font-bold text-foreground px-2 min-w-[56px] text-center">
            GW {displayGW || "—"}
            {atCurrent && currentGW > 0 && (
              <span className="ml-1 text-[8px] font-semibold text-primary uppercase">Live</span>
            )}
            {atFuture && (
              <span className="ml-1 text-[8px] font-semibold text-caution uppercase">Plan</span>
            )}
          </span>
          <button
            onClick={goForward}
            disabled={displayGW >= 38}
            className="p-1 rounded-md hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-4 shrink-0">
          <div className="flex items-center gap-1.5">
            <TrendingUp size={14} className="text-primary" />
            <div>
              <p className="text-[9px] text-muted-foreground leading-none">Points</p>
              <p className="text-sm font-bold text-foreground leading-none mt-0.5">
                {totalPoints > 0 ? totalPoints.toLocaleString() : "—"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <Trophy size={14} className="text-caution" />
            <div>
              <p className="text-[9px] text-muted-foreground leading-none">Rank</p>
              <p className="text-sm font-bold text-foreground leading-none mt-0.5">
                {overallRank > 0 ? overallRank.toLocaleString() : "—"}
              </p>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
