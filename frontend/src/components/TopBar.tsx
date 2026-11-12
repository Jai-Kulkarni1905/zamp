import { LayoutDashboard, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate, useSearchParams } from "react-router";
import { api, DATA_CHANGED } from "../lib/api";
import { useAutoRefresh } from "../lib/useAutoRefresh";
import { cx } from "./ui/primitives";

function SearchBox() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const onDashboard = location.pathname === "/";
  const [value, setValue] = useState(onDashboard ? (params.get("q") ?? "") : "");
  const input = useRef<HTMLInputElement>(null);

  // Keep the box in sync when the dashboard clears its search.
  useEffect(() => {
    if (onDashboard) setValue(params.get("q") ?? "");
  }, [onDashboard, params]);

  // "/" focuses search, like the reference's shortcut hint.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const apply = (q: string) => {
    const next = new URLSearchParams(onDashboard ? params : undefined);
    if (q) next.set("q", q);
    else next.delete("q");
    if (next.get("tab") === "pos") next.delete("tab");
    navigate({ pathname: "/", search: next.toString() }, { replace: onDashboard });
  };

  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        apply(value.trim());
      }}
      className="relative w-full max-w-sm"
    >
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-4" aria-hidden />
      <input
        ref={input}
        type="search"
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          if (onDashboard) apply(e.target.value.trim());
        }}
        placeholder="Search invoices, vendors, POs..."
        aria-label="Search runs"
        className="h-8 w-full rounded-control border border-line bg-sunken pr-8 pl-8 text-sm text-ink placeholder:text-ink-4 focus:border-accent-500 focus:bg-surface focus:shadow-focus focus:outline-none"
      />
      <kbd className="num pointer-events-none absolute top-1/2 right-2 hidden -translate-y-1/2 rounded-chip border border-line bg-surface px-1 text-[10px] text-ink-4 sm:block">
        /
      </kbd>
    </form>
  );
}

export const BRAND = { name: "Tally", tagline: "Invoices Matched, hassle detached" } as const;

export function TopBar() {
  const location = useLocation();
  // The review badge refreshes on navigation and every 10s.
  const stats = useAutoRefresh(() => api.stats(), [location.pathname, location.search], { fast: true, fastMs: 10000 });
  const queue = stats.data?.review_queue ?? 0;
  const { refresh } = stats;
  useEffect(() => {
    const onChange = () => void refresh();
    window.addEventListener(DATA_CHANGED, onChange);
    return () => window.removeEventListener(DATA_CHANGED, onChange);
  }, [refresh]);

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-3 px-4 sm:gap-4 sm:px-6">
        <Link to="/" className="flex shrink-0 items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-control bg-ink text-sm font-bold text-white">T</span>
          <span className="hidden leading-tight sm:block">
            <span className="block text-base font-semibold text-ink">{BRAND.name}</span>
            <span className="hidden text-xs text-ink-3 lg:block">{BRAND.tagline}</span>
          </span>
        </Link>

        <nav className="flex shrink-0 items-center gap-1">
          <NavLink
            to={queue ? "/?tab=review" : "/"}
            className={() =>
              cx(
                "inline-flex h-8 items-center gap-1.5 rounded-control px-2.5 text-sm font-semibold",
                location.pathname === "/" ? "bg-accent-50 text-accent-800" : "text-ink-2 hover:bg-sunken",
              )
            }
          >
            <LayoutDashboard className="size-4" aria-hidden />
            <span className="hidden sm:inline">Dashboard</span>
            {queue > 0 && (
              <span className="num rounded-full bg-accent-600 px-1.5 text-[11px] leading-5 text-white" title={`${queue} waiting for review`}>
                {queue}
                <span className="hidden md:inline"> to review</span>
              </span>
            )}
          </NavLink>
        </nav>

        <div className="flex min-w-0 flex-1 justify-end sm:justify-center">
          <SearchBox />
        </div>

      </div>
    </header>
  );
}
