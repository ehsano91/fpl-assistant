import { Users, Lightbulb, Newspaper, Database, ArrowLeftRight } from "lucide-react";

export type TabId = "team" | "recs" | "transfers" | "briefing" | "data";

const tabs: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "team", label: "My Team", icon: Users },
  { id: "recs", label: "Recs", icon: Lightbulb },
  { id: "transfers", label: "Transfers", icon: ArrowLeftRight },
  { id: "briefing", label: "Briefing", icon: Newspaper },
  { id: "data", label: "Data", icon: Database },
];

export default function BottomNav({ active, onTabChange }: { active: TabId; onTabChange: (t: TabId) => void }) {
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-card/95 backdrop-blur-md border-t border-border z-50">
      <div className="max-w-5xl mx-auto flex justify-around py-2">
        {tabs.map((t) => {
          const Icon = t.icon;
          const isActive = active === t.id;
          return (
            <button
              key={t.id}
              onClick={() => onTabChange(t.id)}
              className={`flex flex-col items-center gap-0.5 px-2 py-1.5 transition-colors ${isActive ? "nav-active" : "nav-inactive"}`}
            >
              <Icon size={20} strokeWidth={isActive ? 2.5 : 1.5} />
              <span className="text-[10px] font-medium">{t.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
