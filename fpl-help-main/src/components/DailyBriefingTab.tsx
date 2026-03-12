import { useEffect, useState } from "react";
import { useAppData } from "@/context/AppDataContext";
import { AlertCircle, CheckCircle, XCircle, AlertTriangle, Radio, Flame, Eye } from "lucide-react";

const statusIcons = {
  injury:    <XCircle     size={14} className="text-danger"   />,
  returning: <CheckCircle size={14} className="text-primary"  />,
  suspended: <AlertCircle size={14} className="text-danger"   />,
  flagged:   <AlertTriangle size={14} className="text-caution" />,
};

const sourceShort: Record<string, string> = {
  "LetsTalkFPL (YouTube)":         "LetsTalkFPL",
  "FPL Mate (YouTube)":            "FPL Mate",
  "FPL General (YouTube)":         "FPL General",
  "FPL Pod (Official PL Podcast)": "FPL Pod",
  "BBC Sport Football":            "BBC Sport",
  "The Guardian Football":         "Guardian",
};

const sourceColor: Record<string, string> = {
  "LetsTalkFPL (YouTube)":         "bg-primary/20 text-primary",
  "FPL Mate (YouTube)":            "bg-teal/20 text-teal",
  "FPL General (YouTube)":         "bg-primary/15 text-primary",
  "FPL Pod (Official PL Podcast)": "bg-caution/20 text-caution",
  "BBC Sport Football":            "bg-muted text-muted-foreground",
  "The Guardian Football":         "bg-muted text-muted-foreground",
};

const posColors: Record<string, string> = {
  GK:  "bg-caution/20 text-caution",
  DEF: "bg-teal/20 text-teal",
  MID: "bg-primary/20 text-primary",
  FWD: "bg-danger/20 text-danger",
};

function Countdown({ deadlineTime }: { deadlineTime: string | null }) {
  const [diff, setDiff] = useState(() =>
    deadlineTime ? new Date(deadlineTime).getTime() - Date.now() : 0
  );
  useEffect(() => {
    if (!deadlineTime) return;
    const t = setInterval(() => setDiff(new Date(deadlineTime).getTime() - Date.now()), 1000);
    return () => clearInterval(t);
  }, [deadlineTime]);

  if (!deadlineTime || diff <= 0) return null;
  const hrs  = Math.floor(diff / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  const secs = Math.floor((diff % 60000) / 1000);

  return (
    <div className="pill-card text-center">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Next Deadline</p>
      <p className="text-3xl font-bold text-primary font-mono">
        {String(hrs).padStart(2, "0")}:{String(mins).padStart(2, "0")}:{String(secs).padStart(2, "0")}
      </p>
    </div>
  );
}

export default function DailyBriefingTab() {
  const {
    briefingSummary, newsPills, briefingDate, gameweek, deadlineTime,
    communityHeadlines, hotPlayers, squadWatch,
  } = useAppData();

  return (
    <div className="pb-6 px-4 space-y-5 max-w-2xl mx-auto">

      {/* Header */}
      <div>
        <p className="text-xs text-muted-foreground">{briefingDate}</p>
        <div className="flex items-center gap-2 mt-1">
          <h2 className="text-xl font-bold text-foreground">Daily Briefing</h2>
          {gameweek > 0 && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary text-primary-foreground">
              GW{gameweek}
            </span>
          )}
        </div>
      </div>

      {/* Summary */}
      <div className="pill-card">
        <p className="text-sm text-foreground/90 leading-relaxed">{briefingSummary}</p>
      </div>

      {/* Injury / fitness pills */}
      {newsPills.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Player News</p>
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
            {newsPills.map((pill, i) => (
              <div key={i} className="pill-card flex items-center gap-2 whitespace-nowrap shrink-0 py-2">
                {statusIcons[pill.status]}
                <div>
                  <p className="text-xs font-semibold text-foreground">{pill.player}</p>
                  <p className="text-[10px] text-muted-foreground">{pill.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Community Headlines */}
      {communityHeadlines.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Radio size={14} className="text-primary" />
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Latest from Podcasts & YouTube
            </p>
          </div>
          <div className="space-y-2">
            {communityHeadlines.map((h, i) => (
              <div key={i} className="pill-card flex items-start gap-2 py-2">
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5 ${sourceColor[h.source] ?? "bg-muted text-muted-foreground"}`}>
                  {sourceShort[h.source] ?? h.source}
                </span>
                <p className="text-xs text-foreground leading-snug">{h.headline}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hot Players (non-squad, community buzz) */}
      {hotPlayers.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Flame size={14} className="text-danger" />
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Hot Topics — Not In Your Squad
            </p>
          </div>
          <div className="space-y-2">
            {hotPlayers.map((p) => (
              <div key={p.id} className="pill-card flex items-start gap-3 py-2">
                <div className="shrink-0 text-center min-w-[48px]">
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded block mb-1 ${posColors[p.position] ?? "bg-muted text-muted-foreground"}`}>
                    {p.position}
                  </span>
                  <p className="text-[10px] font-bold text-foreground">{p.name}</p>
                  <p className="text-[9px] text-muted-foreground">{p.team}</p>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold text-primary">{p.xP} xP</span>
                    <span className="text-[10px] text-muted-foreground">📡 {p.buzz} buzz</span>
                  </div>
                  {p.headline && (
                    <p className="text-[10px] text-muted-foreground leading-snug line-clamp-2">{p.headline}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Squad Watch */}
      {squadWatch.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Eye size={14} className="text-caution" />
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Your Squad in the News
            </p>
          </div>
          <div className="space-y-2">
            {squadWatch.map((p, i) => (
              <div key={i} className="pill-card flex items-start gap-3 py-2">
                <div className="shrink-0 min-w-[52px]">
                  <p className="text-[10px] font-bold text-foreground">{p.name}</p>
                  <p className="text-[9px] text-muted-foreground">{p.team}</p>
                  <span className="text-[9px] text-muted-foreground">📡 {p.buzz}</span>
                </div>
                <p className="text-[10px] text-muted-foreground leading-snug flex-1 line-clamp-3">{p.headline}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <Countdown deadlineTime={deadlineTime} />
    </div>
  );
}
