import { useAppData } from "@/context/AppDataContext";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle, AlertTriangle, RefreshCw } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { API_BASE } from "@/lib/api";

export default function DataTab() {
  const { dataSources, lastRefresh } = useAppData();
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Stop polling on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setStatusMsg("Starting pipeline…");

    try {
      await fetch(`${API_BASE}/refresh`, { method: "POST" });
    } catch {
      setRefreshing(false);
      setStatusMsg("Could not reach server.");
      return;
    }

    setStatusMsg("Fetching FPL data…");

    // Poll /status every 3s until pipelineRunning goes false
    pollRef.current = setInterval(async () => {
      try {
        const res  = await fetch(`${API_BASE}/status`);
        const data = await res.json();
        if (!data.pipelineRunning) {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          await queryClient.invalidateQueries();
          setRefreshing(false);
          setStatusMsg("");
        }
      } catch {
        // server temporarily busy — keep polling
      }
    }, 3000);
  };

  return (
    <div className="pb-4 px-4 space-y-4 max-w-2xl mx-auto">
      <h2 className="text-xl font-bold text-foreground">Data Sources</h2>

      <div className="pill-card">
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Last Full Refresh</p>
        <p className="text-sm font-semibold text-foreground">{lastRefresh}</p>
      </div>

      <div className="space-y-2">
        {dataSources.map((src) => (
          <div key={src.name} className="pill-card flex items-center justify-between">
            <div className="flex items-center gap-2">
              {src.status === "ok" ? (
                <CheckCircle size={16} className="text-primary" />
              ) : (
                <AlertTriangle size={16} className="text-caution" />
              )}
              <div>
                <span className="text-sm text-foreground">{src.name}</span>
                {src.count !== undefined && (
                  <span className="ml-2 text-[10px] text-muted-foreground">{src.count.toLocaleString()} rows</span>
                )}
              </div>
            </div>
            <span className="text-[10px] text-muted-foreground">{src.lastUpdate}</span>
          </div>
        ))}
      </div>

      <button
        onClick={handleRefresh}
        disabled={refreshing}
        className="w-full py-3 rounded-xl bg-teal text-primary-foreground font-semibold flex items-center justify-center gap-2 transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        <RefreshCw size={18} className={refreshing ? "animate-spin" : ""} />
        {refreshing ? (statusMsg || "Refreshing…") : "Refresh Now"}
      </button>

      <p className="text-center text-[10px] text-muted-foreground">
        All data stored locally on your device
      </p>
    </div>
  );
}
