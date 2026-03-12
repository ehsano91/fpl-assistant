import { useEffect, useState } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import type { Player, Position } from "@/lib/api";
import { API_BASE } from "@/lib/api";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart, Cell } from "recharts";
import { Shield, TrendingUp, Users, Calendar, Activity, Target, Footprints } from "lucide-react";

interface Props {
  player: Player | null;
  open: boolean;
  onClose: () => void;
}

interface PlayerDetail {
  id: number;
  name: string;
  shortName: string;
  team: string;
  price: number;
  goalsScored: number;
  assists: number;
  cleanSheets: number;
  yellowCards: number;
  redCards: number;
  bonus: number;
  minutes: number;
  ictIndex: number;
  selectedByPct: number;
  form: number;
  pointsPerGame: number;
  totalPoints: number;
  fixtures: { gw: number; opponent: string; home: boolean; fdr: number }[];
  ownershipTrend: { gw: string; pct: number }[];
}

const fdrColors: Record<number, string> = {
  1: "bg-primary/80",
  2: "bg-primary/60",
  3: "bg-caution/60",
  4: "bg-danger/50",
  5: "bg-danger/80",
};

const fdrTextColors: Record<number, string> = {
  1: "text-primary-foreground",
  2: "text-primary-foreground",
  3: "text-primary-foreground",
  4: "text-foreground",
  5: "text-foreground",
};

const positionBadgeColors: Record<Position, string> = {
  GK: "bg-caution/20 text-caution",
  DEF: "bg-teal/20 text-teal",
  MID: "bg-primary/20 text-primary",
  FWD: "bg-danger/20 text-danger",
};

const fitnessLabels = { fit: "Available", doubt: "Doubtful", out: "Injured/Suspended" };
const fitnessColors = { fit: "text-primary", doubt: "text-caution", out: "text-danger" };

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border rounded-lg px-2 py-1 shadow-lg">
      <p className="text-[10px] text-muted-foreground">{payload[0].payload.gw || `GW+${payload[0].payload.idx + 1}`}</p>
      <p className="text-xs font-bold text-primary">{payload[0].value}{payload[0].dataKey === "pct" ? "%" : ""}</p>
    </div>
  );
};

export default function PlayerModal({ player, open, onClose }: Props) {
  const [detail, setDetail] = useState<PlayerDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !player) { setDetail(null); return; }
    setLoading(true);
    fetch(`${API_BASE}/player?id=${player.id}`)
      .then((r) => r.json())
      .then((d) => { setDetail(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [open, player?.id]);

  if (!player) return null;

  const maxXP = Math.max(...player.xPForecast, 0.1);
  const forecastData = player.xPForecast.map((xp, i) => ({ idx: i, xp, label: `+${i + 1}` }));

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="bg-card border-border max-w-[480px] rounded-2xl p-0 max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="p-5 pb-3 border-b border-border">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${positionBadgeColors[player.position]}`}>
                  {player.position}
                </span>
                <span className={`text-xs font-medium ${fitnessColors[player.fitness]}`}>
                  {fitnessLabels[player.fitness]}
                </span>
              </div>
              <h2 className="text-lg font-bold text-foreground">{player.name}</h2>
              <p className="text-sm text-muted-foreground">
                {player.team}{detail ? ` · £${detail.price}m` : ""}
              </p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold text-primary">{player.xP}</p>
              <p className="text-[10px] text-muted-foreground">xP (next GW)</p>
              {detail && (
                <p className="text-[10px] text-muted-foreground mt-0.5">{detail.totalPoints} pts total</p>
              )}
            </div>
          </div>
        </div>

        {/* Key stats grid */}
        <div className="px-5 py-3">
          {loading ? (
            <div className="grid grid-cols-4 gap-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="bg-muted rounded-lg p-2 h-14 animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-4 gap-2">
              {[
                { icon: Target,    label: "Goals",    value: detail?.goalsScored ?? "—" },
                { icon: Footprints,label: "Assists",  value: detail?.assists ?? "—" },
                { icon: Activity,  label: "ICT",      value: detail ? detail.ictIndex.toFixed(1) : "—" },
                { icon: TrendingUp,label: "Bonus",    value: detail?.bonus ?? "—" },
                { icon: Shield,    label: "CS",       value: detail?.cleanSheets ?? "—" },
                { icon: Calendar,  label: "Minutes",  value: detail?.minutes?.toLocaleString() ?? "—" },
                { icon: Users,     label: "Selected", value: detail ? `${detail.selectedByPct}%` : "—" },
                { icon: Activity,  label: "Form",     value: detail?.form?.toFixed(1) ?? "—" },
              ].map((stat, i) => {
                const Icon = stat.icon;
                return (
                  <div key={i} className="bg-muted rounded-lg p-2 text-center">
                    <Icon size={14} className="text-muted-foreground mx-auto mb-1" />
                    <p className="text-sm font-bold text-foreground">{stat.value}</p>
                    <p className="text-[9px] text-muted-foreground">{stat.label}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* xP Forecast */}
        <div className="px-5 py-3 border-t border-border">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">xP Forecast (GW+1 to +6)</p>
          <div className="h-28">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={forecastData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: "hsl(207, 25%, 70%)" }} axisLine={false} tickLine={false} />
                <YAxis hide domain={[0, "dataMax + 2"]} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="xp" radius={[4, 4, 0, 0]}>
                  {forecastData.map((entry, i) => (
                    <Cell key={i} fill={`hsl(153, 100%, ${40 + (entry.xp / maxXP) * 20}%)`} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Fixture Difficulty */}
        <div className="px-5 py-3 border-t border-border">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Upcoming Fixtures (FDR)</p>
          {loading ? (
            <div className="grid grid-cols-6 gap-1.5">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="rounded-lg h-10 bg-muted animate-pulse" />
              ))}
            </div>
          ) : detail?.fixtures?.length ? (
            <>
              <div className="grid grid-cols-6 gap-1.5">
                {detail.fixtures.map((f) => (
                  <div key={f.gw} className={`rounded-lg p-1.5 text-center ${fdrColors[f.fdr] ?? "bg-muted"}`}>
                    <p className={`text-[10px] font-bold ${fdrTextColors[f.fdr] ?? ""}`}>{f.opponent}</p>
                    <p className={`text-[9px] ${fdrTextColors[f.fdr] ?? ""} opacity-80`}>{f.home ? "H" : "A"}</p>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2 mt-2 justify-center">
                {[1, 2, 3, 4, 5].map((fdr) => (
                  <div key={fdr} className="flex items-center gap-1">
                    <div className={`w-3 h-3 rounded-sm ${fdrColors[fdr]}`} />
                    <span className="text-[9px] text-muted-foreground">{fdr}</span>
                  </div>
                ))}
                <span className="text-[9px] text-muted-foreground ml-1">(1=easy, 5=hard)</span>
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground">No upcoming fixtures</p>
          )}
        </div>

        {/* Ownership Trend */}
        {(detail?.ownershipTrend?.length ?? 0) > 1 && (
          <div className="px-5 py-3 pb-5 border-t border-border">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              Ownership Trend (last {detail!.ownershipTrend.length} GWs)
            </p>
            <div className="h-24">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={detail!.ownershipTrend} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
                  <defs>
                    <linearGradient id="ownerGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="hsl(170, 80%, 45%)" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="hsl(170, 80%, 45%)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="gw" tick={{ fontSize: 9, fill: "hsl(207, 25%, 70%)" }} axisLine={false} tickLine={false} />
                  <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="pct" stroke="hsl(170, 80%, 45%)" strokeWidth={1.5} fill="url(#ownerGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
