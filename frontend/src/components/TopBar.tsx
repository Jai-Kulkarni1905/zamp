import { FileUp, FlaskConical, Radio } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router";
import { api } from "../lib/api";
import type { Health } from "../lib/types";
import { cx } from "./ui/primitives";

export function TopBar() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    api.health().then(setHealth, () => setHealth(null));
  }, []);

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-4 px-4 sm:px-6">
        <Link to="/" className="flex shrink-0 items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-control bg-ink text-xs font-bold text-white">AP</span>
          <span className="hidden leading-tight sm:block">
            <span className="block text-base font-semibold text-ink">AP Invoice Agent</span>
            <span className="block text-xs text-ink-3">Finance Ops</span>
          </span>
        </Link>

        <nav className="flex items-center gap-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              cx(
                "inline-flex h-8 items-center gap-1.5 rounded-control px-3 text-sm font-semibold",
                isActive ? "bg-accent-50 text-accent-800" : "text-ink-2 hover:bg-sunken",
              )
            }
          >
            <FileUp className="size-4" aria-hidden />
            Upload
          </NavLink>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {health && (
            <span
              title={health.llm_mode === "live" ? "Gemini is called on a cache miss" : "Recorded extractions only, no Gemini calls"}
              className={cx(
                "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium",
                health.llm_mode === "live" ? "border-accent-200 bg-accent-50 text-accent-700" : "border-line bg-sunken text-ink-2",
              )}
            >
              {health.llm_mode === "live" ? <Radio className="size-3.5" aria-hidden /> : <FlaskConical className="size-3.5" aria-hidden />}
              <span className="hidden sm:inline">{health.llm_mode === "live" ? "Live Gemini" : "Fixture mode"}</span>
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
