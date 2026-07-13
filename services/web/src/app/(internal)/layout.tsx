import { TopBar } from "@/components/top-bar";
import { InternalSidebar } from "@/components/internal/sidebar";

export default function InternalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <InternalSidebar />
        <main className="flex flex-1 flex-col overflow-hidden min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}
