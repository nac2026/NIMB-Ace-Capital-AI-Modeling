"use client";

// Slim sidebar for the (internal) workspace — internal file uploads. Mirrors the
// speculative sidebar's collapse/tooltip behaviour, but omits the ModeSwitcher
// (that component is hard-typed research|speculative; cross-module navigation is
// handled by the top-bar Launcher).

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import {
  Upload, BookOpen, ExternalLink, ShieldAlert,
  PanelLeftClose, PanelLeft, Database,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { HealthDot } from "@/components/health-dot";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { useCollapseState } from "@/lib/use-collapse-state";

const NAV = [
  { href: "/internal/file/uploads", label: "File uploads", icon: Upload, exact: true },
];

export function InternalSidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useCollapseState("nrc.sidebar_collapsed", false);

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
            <span className="text-[12px] font-medium tracking-tight text-fg-muted">· Internal</span>
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

      {!collapsed && (
        <div className="px-3 pt-4 pb-1">
          <div className="label px-2">Workspace</div>
        </div>
      )}

      <nav className={cn("flex-1 space-y-px", collapsed ? "px-1.5 pt-3" : "px-2")}>
        {NAV.map(({ href, label, icon: Icon, exact }) => (
          <NavLink key={href} href={href} label={label} Icon={Icon} pathname={pathname} collapsed={collapsed} exact={exact} />
        ))}
      </nav>

      <div className={cn("pt-2", collapsed ? "px-1.5" : "px-2")}>
        <div className="mx-1 border-t" style={{ borderColor: "var(--border-subtle)" }} />
        <div className="space-y-px pt-2">
          <NavLink
            href="/surveillance"
            label="Trade surveillance"
            Icon={ShieldAlert}
            pathname={pathname}
            collapsed={collapsed}
          />
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
  external?: boolean;
}) {
  const active = external ? false : exact ? pathname === href : (pathname === href || (href !== "/" && pathname.startsWith(href)));
  const targetProps = external ? { target: "_blank" as const, rel: "noopener noreferrer" } : {};
  return (
    <Link
      href={href}
      {...targetProps}
      className={cn(
        "group relative flex items-center gap-2.5 text-[13px] transition-colors",
        collapsed ? "justify-center rounded-md px-0 py-2" : "px-2 py-1.5 rounded-md",
        active ? "bg-bg-hover font-medium" : "text-fg-muted hover:bg-bg-hover hover:text-fg",
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
