import { TopBar } from "@/components/top-bar";
import { SpeculativeSidebar } from "@/components/speculative/sidebar";

export default function SpeculativeLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <SpeculativeSidebar />
        <main className="flex flex-1 flex-col overflow-hidden min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}
