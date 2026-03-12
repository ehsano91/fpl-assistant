import { useState } from "react";
import { Loader2, WifiOff } from "lucide-react";
import BottomNav, { TabId } from "@/components/BottomNav";
import Header from "@/components/Header";
import MyTeamTab from "@/components/MyTeamTab";
import RecommendationsTab from "@/components/RecommendationsTab";
import DailyBriefingTab from "@/components/DailyBriefingTab";
import DataTab from "@/components/DataTab";
import TransferPlannerTab from "@/components/TransferPlannerTab";
import { AppDataProvider, useAppData } from "@/context/AppDataContext";

const tabs: Record<TabId, React.FC> = {
  team:      MyTeamTab,
  recs:      RecommendationsTab,
  transfers: TransferPlannerTab,
  briefing:  DailyBriefingTab,
  data:      DataTab,
};

function AppShell() {
  const [activeTab, setActiveTab] = useState<TabId>("team");
  const { isLoading, isError, errorMsg } = useAppData();
  const ActiveComponent = tabs[activeTab];

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4">
        <Loader2 size={40} className="text-primary animate-spin" />
        <p className="text-sm text-muted-foreground">Loading your FPL data…</p>
        <p className="text-xs text-muted-foreground opacity-60">Connecting to local API server on port 8000</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4 px-6 text-center">
        <WifiOff size={40} className="text-danger" />
        <p className="text-lg font-bold text-foreground">API Server Offline</p>
        <p className="text-sm text-muted-foreground max-w-sm">
          The local API server isn't responding. Start it in a terminal:
        </p>
        <code className="bg-muted text-foreground rounded-lg px-4 py-2 text-sm font-mono">
          python3 engine/api_server.py
        </code>
        <p className="text-xs text-muted-foreground mt-2 whitespace-pre-line max-w-sm">{errorMsg}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="max-w-5xl mx-auto pt-4 pb-20">
        <ActiveComponent />
      </div>
      <BottomNav active={activeTab} onTabChange={setActiveTab} />
    </div>
  );
}

export default function Index() {
  return (
    <AppDataProvider>
      <AppShell />
    </AppDataProvider>
  );
}
