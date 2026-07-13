"use client";

import { use, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ScripHeader } from "@/components/scrip/header";
import { TabNav, SCRIP_TABS, visibleTabs, type ScripTab } from "@/components/scrip/tab-nav";
import { TabOverview }      from "@/components/scrip/tab-overview";
import { TabOwnership }     from "@/components/scrip/tab-ownership";
import { TabPerformance }   from "@/components/scrip/tab-performance";
import { TabFundamentals }  from "@/components/scrip/tab-fundamentals";
import { TabValuation }     from "@/components/scrip/tab-valuation";
import { TabAssetQuality }  from "@/components/scrip/tab-asset-quality";
import { TabCapital }       from "@/components/scrip/tab-capital";
import { TabIncome }        from "@/components/scrip/tab-income";
import { TabTechnicals }    from "@/components/scrip/tab-technicals";
import { TabQuality }       from "@/components/scrip/tab-quality";
import { TabFloorsheet }    from "@/components/scrip/tab-floorsheet";
import { TabNewsSentiment } from "@/components/scrip/tab-news-sentiment";
import { FinancialsExplorer } from "@/components/scrip/financials-explorer";
import { SmtmFundamentals } from "@/components/scrip/smtm-fundamentals";

export default function ScripDetailPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  const scrip = decodeURIComponent(symbol).toUpperCase();

  const [tab, setTab] = useState<ScripTab>("overview");

  // URL hash ↔ tab sync. Hash-based per plan so analysts can deep-link.
  useEffect(() => {
    const fromHash = () => {
      const h = window.location.hash.slice(1) as ScripTab;
      if (SCRIP_TABS.includes(h)) setTab(h);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);

  function handleTabChange(t: ScripTab) {
    setTab(t);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.hash = t;
      window.history.replaceState(null, "", url.toString());
    }
  }

  const summary = useQuery({
    queryKey: ["scrip-summary", scrip],
    queryFn: () => api.scrip.summary(scrip),
  });

  // Sector-aware: if the active tab isn't available for this sector, fall back.
  const allowed = visibleTabs(summary.data?.sector);
  const activeTab: ScripTab = allowed.includes(tab) ? tab : "overview";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <ScripHeader scrip={scrip} summary={summary.data} />
      <TabNav active={activeTab} onChange={handleTabChange} sector={summary.data?.sector} />
      <div className="flex-1 overflow-y-auto px-6 py-5 bg-bg">
        {activeTab === "overview"       && <TabOverview      scrip={scrip} />}
        {activeTab === "performance"    && <TabPerformance   scrip={scrip} />}
        {activeTab === "fundamentals"   && <TabFundamentals  scrip={scrip} />}
        {activeTab === "financials"     && (
          <div className="flex flex-col gap-5">
            <SmtmFundamentals scrip={scrip} />
            <FinancialsExplorer scrip={scrip} />
          </div>
        )}
        {activeTab === "valuation"      && <TabValuation     scrip={scrip} />}
        {activeTab === "asset-quality"  && <TabAssetQuality  scrip={scrip} />}
        {activeTab === "capital"        && <TabCapital       scrip={scrip} />}
        {activeTab === "income"         && <TabIncome        scrip={scrip} />}
        {activeTab === "technicals"     && <TabTechnicals    scrip={scrip} />}
        {activeTab === "quality"        && <TabQuality       scrip={scrip} />}
        {activeTab === "floorsheet"     && <TabFloorsheet    scrip={scrip} />}
        {activeTab === "ownership"      && <TabOwnership     scrip={scrip} />}
        {activeTab === "news"           && <TabNewsSentiment scrip={scrip} />}
      </div>
    </div>
  );
}
