"use client";
// Left nav. Expanded: 240px with labels. Collapsed: 56px, icons only.
// State persists across routes/reloads via localStorage. Cmd+B toggles.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import {
  Activity, LayoutGrid, MessageSquare, GitCompareArrows, Filter,
  Trophy, TrendingDown, Coins, Crosshair, RotateCcw,
  PanelLeftClose, PanelLeft, BookOpen, ExternalLink, Database,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { HealthDot } from "./health-dot";
import { ThemeToggle } from "./theme/theme-toggle";
import { ModeSwitcher } from "./mode-switcher";
import { useCollapseState } from "@/lib/use-collapse-state";

const MAIN_LINKS = [
  { href: "/dashboard", label: "Dashboard",     icon: LayoutGrid },
  { href: "/compare",   label: "Compare",        icon: GitCompareArrows },
  { href: "/live",      label: "Live Market",    icon: Activity },
  { href: "/chat",      label: "Chat history",   icon: MessageSquare },
];

const SCREENS = [
  { href: "/screen/top-quality",   label: "Top quality",       icon: Trophy },
  { href: "/screen/cheap-vs-self", label: "Cheap vs own",      icon: TrendingDown },
  { href: "/screen/high-yield",    label: "High yield",        icon: Coins },
  { href: "/screen/contrarian",    label: "Contrarian bets",   icon: Crosshair },
  { href: "/screen/turnaround",    label: "Turnaround",        icon: RotateCcw },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useCollapseState("nrc.sidebar_collapsed", false);

  // Cmd+B / Ctrl+B toggles the sidebar globally.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setCollapsed((p) => !p);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setCollapsed]);

  // Auto-collapse when user focuses chat input, auto-expand never.
  useEffect(() => {
    function onFocus() { setCollapsed(true); }
    window.addEventListener("nrc:chat-focus", onFocus);
    return () => window.removeEventListener("nrc:chat-focus", onFocus);
  }, [setCollapsed]);

  const width = collapsed ? 56 : 240;

  return (
    <aside
      className="flex h-full shrink-0 flex-col border-r border-border-subtle bg-bg-subtle transition-[width] duration-200 ease-out"
      style={{ width }}
    >
      <div className={cn("flex h-[52px] items-center border-b border-border-subtle", collapsed ? "justify-center px-0" : "justify-between px-4")}>
        {!collapsed && (
          <div className="flex items-baseline gap-1.5">
            <span className="text-[13px] font-bold tracking-tight" style={{ color: "var(--brand)" }}>NIMB Ace</span>
            <span className="text-[12px] font-medium tracking-tight text-fg-muted">· Research</span>
          </div>
        )}
        <button
          onClick={() => setCollapsed((p) => !p)}
          title={collapsed ? "Expand (⌘B)" : "Collapse (⌘B)"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex h-7 w-7 items-center justify-center rounded-md text-fg-muted transition-colors hover:bg-bg-hover hover:text-fg"
        >
          {collapsed ? <PanelLeft className="h-[14px] w-[14px]" strokeWidth={1.75} /> : <PanelLeftClose className="h-[14px] w-[14px]" strokeWidth={1.75} />}
        </button>
      </div>

      {/* Mode switcher pinned at top */}
      <div className={cn("border-b", collapsed ? "py-2" : "px-3 pt-3 pb-2")} style={{ borderColor: "var(--border-subtle)" }}>
        <ModeSwitcher current="research" collapsed={collapsed} />
      </div>

      {!collapsed && (
        <div className="px-3 pt-4 pb-1">
          <div className="label px-2">Workspace</div>
        </div>
      )}

      <nav className={cn("space-y-px", collapsed ? "px-1.5 pt-3" : "px-2")}>
        {MAIN_LINKS.map(({ href, label, icon: Icon }) => (
          <NavLink key={href} href={href} label={label} Icon={Icon} pathname={pathname} collapsed={collapsed} />
        ))}
      </nav>

      {!collapsed && (
        <div className="px-3 pt-5 pb-1">
          <div className="label px-2 inline-flex items-center gap-1.5">
            <Filter className="h-3 w-3" strokeWidth={2} />
            Screens
          </div>
        </div>
      )}

      <nav className={cn("flex-1 space-y-px", collapsed ? "px-1.5 pt-3" : "px-2")}>
        {SCREENS.map(({ href, label, icon: Icon }) => (
          <NavLink key={href} href={href} label={label} Icon={Icon} pathname={pathname} collapsed={collapsed} exact />
        ))}
      </nav>

      {/* Separator before utility / reference links so they read as distinct
          from the main operational pages above. */}
      <div className={cn("pt-2", collapsed ? "px-1.5" : "px-2")}>
        <div className="mx-1 border-t" style={{ borderColor: "var(--border-subtle)" }} />
        <div className="space-y-px pt-2">
          <NavLink
            href="/data-coverage"
            label="Data coverage"
            Icon={Database}
            pathname={pathname}
            collapsed={collapsed}
          />
          <NavLink
            href="/help"
            label="Help & docs"
            Icon={BookOpen}
            pathname={pathname}
            collapsed={collapsed}
            external
          />
        </div>
      </div>

      <div className={cn("mt-2 flex items-center border-t border-border-subtle", collapsed ? "h-[88px] flex-col gap-1 py-2" : "h-[44px] justify-between px-3")}>
        <HealthDot />
        <ThemeToggle />
      </div>
    </aside>
  );
}

function NavLink({
  href, label, Icon, pathname, collapsed, exact, external,
}: {
  href: string;
  label: string;
  Icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  pathname: string;
  collapsed: boolean;
  exact?: boolean;
  // Always opens in a new tab. Used for reference surfaces (like /help)
  // so staff can keep the docs open while working elsewhere.
  external?: boolean;
}) {
  const active = external
    ? false
    : exact
      ? pathname === href
      : (pathname === href || (href !== "/" && pathname.startsWith(href)));
  const targetProps = external
    ? { target: "_blank" as const, rel: "noopener noreferrer" }
    : {};
  return (
    <Link
      href={href}
      {...targetProps}
      className={cn(
        "group relative flex items-center gap-2.5 text-[13px] transition-colors",
        collapsed ? "justify-center rounded-md px-0 py-2" : "px-2 py-1.5 rounded-md",
        active
          ? "bg-bg-hover font-medium"
          : "text-fg-muted hover:bg-bg-hover hover:text-fg",
      )}
      style={active ? { color: "var(--brand)" } : undefined}
    >
      <Icon className="h-[14px] w-[14px] shrink-0" strokeWidth={1.75} />
      {!collapsed && (
        <span className="flex flex-1 items-center justify-between gap-1.5 truncate">
          <span className="truncate">{label}</span>
          {external && <ExternalLink className="h-3 w-3 shrink-0 text-fg-dim" strokeWidth={1.75} />}
        </span>
      )}
      {collapsed && (
        <span
          role="tooltip"
          className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 -translate-x-1 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium opacity-0 transition-[opacity,transform] duration-150 ease-out delay-150 group-hover:translate-x-0 group-hover:opacity-100"
          style={{ background: "var(--fg)", color: "var(--bg)", boxShadow: "var(--shadow-md)" }}
        >
          {label}{external ? " ↗" : ""}
        </span>
      )}
    </Link>
  );
}
