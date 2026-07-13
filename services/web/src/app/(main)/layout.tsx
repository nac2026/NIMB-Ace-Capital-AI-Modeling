import { Suspense } from "react";
import { TopBar } from "@/components/top-bar";
import { ChatDrawer } from "@/components/chat-drawer/chat-drawer";
import { CommandPalette } from "@/components/command-palette/command-palette";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <main className="flex flex-1 flex-col overflow-hidden min-w-0">
          {children}
        </main>
        <Suspense fallback={null}>
          <ChatDrawer />
        </Suspense>
        <Suspense fallback={null}>
          <CommandPalette />
        </Suspense>
      </div>
    </div>
  );
}
