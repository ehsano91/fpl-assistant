import { useState } from "react";
import { useAppData } from "@/context/AppDataContext";
import type { RecType } from "@/lib/api";
import { ChevronDown, ChevronUp, ArrowDownLeft, ArrowUpRight, Crown, Star, AlertTriangle, Radio } from "lucide-react";

const typeConfig: Record<RecType, { label: string; icon: React.ElementType }> = {
  transfer_in:    { label: "Transfer In",    icon: ArrowDownLeft },
  transfer_out:   { label: "Transfer Out",   icon: ArrowUpRight },
  captain:        { label: "Captain Pick",   icon: Crown },
  starting_xi:    { label: "Starting XI",    icon: Star },
  chip_alert:     { label: "Chip Alert",     icon: AlertTriangle },
  community_buzz: { label: "Community Buzz", icon: Radio },
};

export default function RecommendationsTab() {
  const { recommendations } = useAppData();
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className="pb-4 px-4 space-y-3 max-w-2xl mx-auto">
      <h2 className="text-xl font-bold text-foreground mb-4">Recommendations</h2>
      {recommendations.map((rec) => {
        const cfg  = typeConfig[rec.type];
        const Icon = cfg.icon;
        const isOpen = expanded === rec.id;
        return (
          <div key={rec.id} className={`pill-card ${rec.positive ? "gradient-teal" : "gradient-caution"}`}>
            <div className="flex items-start gap-2 mb-1">
              <Icon size={16} className={rec.positive ? "text-teal" : "text-caution"} />
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{cfg.label}</span>
            </div>
            <h3 className="text-sm font-bold text-foreground">{rec.title}</h3>
            <p className="text-xs text-muted-foreground mt-1">{rec.summary}</p>
            <button
              onClick={() => setExpanded(isOpen ? null : rec.id)}
              className="flex items-center gap-1 mt-2 text-[11px] text-primary font-medium"
            >
              {isOpen ? "Hide" : "Show"} Reasoning
              {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {isOpen && (
              <div className="text-xs text-muted-foreground mt-2 border-t border-border pt-2 leading-relaxed space-y-2">
                {rec.reasoning.split("\n\n").map((block, i) => (
                  <p key={i}>{block}</p>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
