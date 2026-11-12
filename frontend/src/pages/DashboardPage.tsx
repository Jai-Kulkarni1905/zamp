import { CircleCheck, Inbox, LayoutList, Plus, Receipt } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { FilterBar, type FilterValues } from "../components/dashboard/FilterBar";
import { NewPODialog } from "../components/dashboard/NewPODialog";
import { POTable } from "../components/dashboard/POTable";
import { RunsTable } from "../components/dashboard/RunsTable";
import { Dropzone } from "../components/Dropzone";
import { ReviewDialog, type ReviewAction } from "../components/run/ReviewActions";
import { Button, Card, KpiTile } from "../components/ui/primitives";
import { Tabs } from "../components/ui/Tabs";
import { api } from "../lib/api";
import { formatINR, formatMs, formatPct } from "../lib/format";
import type { Decision, Flag, RunSummary, Stats } from "../lib/types";
import { useAutoRefresh } from "../lib/useAutoRefresh";

type TabKey = "all" | "review" | "pos";
const TABS: TabKey[] = ["all", "review", "pos"];

function KpiStrip({ stats }: { stats: Stats | null }) {
  const s = stats;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      <KpiTile
        size="lg"
        label="Runs processed"
        value={s ? s.runs_done : "..."}
        sub={s && s.runs_in_progress ? `${s.runs_in_progress} running` : s && s.runs_error ? `${s.runs_error} errors` : undefined}
        subTone={s && s.runs_in_progress ? "RUNNING" : s && s.runs_error ? "FAIL" : undefined}
      />
      <KpiTile
        size="lg"
        label="Approval rate"
        value={s?.approval_rate !== null && s?.approval_rate !== undefined ? formatPct(s.approval_rate, 0) : "n/a"}
        sub={s ? `${s.decisions.APPROVED} auto-approved` : undefined}
      />
      <KpiTile
        size="lg"
        label="Review queue"
        value={s ? s.review_queue : "..."}
        sub={s ? (s.review_queue ? "waiting" : "clear") : undefined}
        subTone={s ? (s.review_queue ? "WARN" : "PASS") : undefined}
      />
      <KpiTile size="lg" label="Avg processing" value={s?.avg_processing_ms ? formatMs(s.avg_processing_ms) : "n/a"} sub="per invoice" />
      <KpiTile
        size="lg"
        label="Value processed"
        value={s ? formatINR(s.value_processed) : "..."}
        sub={s ? `${formatINR(s.value_approved)} approved` : undefined}
        subTone="PASS"
        className="col-span-2 md:col-span-1"
      />
    </div>
  );
}

export function DashboardPage() {
  const [params, setParams] = useSearchParams();
  const tab: TabKey = TABS.includes(params.get("tab") as TabKey) ? (params.get("tab") as TabKey) : "all";
  const q = params.get("q") ?? "";
  const filters: FilterValues = useMemo(
    () => ({
      decision: params.get("decision") ?? "",
      flag: params.get("flag") ?? "",
      vendor_id: params.get("vendor_id") ?? "",
      date_from: params.get("date_from") ?? "",
      date_to: params.get("date_to") ?? "",
    }),
    [params],
  );

  // Stats are the heartbeat: every 2s while runs are queued or running, every 15s otherwise, so uploads
  // from other tabs or users show up too. Lists re-fetch whenever the counters change (A58).
  const [fast, setFast] = useState(false);
  const stats = useAutoRefresh(() => api.stats(), [], { fast: true, fastMs: fast ? 2000 : 15000 });
  const current = stats.data;
  useEffect(() => setFast((current?.runs_in_progress ?? 0) > 0), [current]);
  const pulse = current
    ? `${current.runs_total}-${current.runs_done}-${current.runs_error}-${current.review_queue}-${current.value_approved}`
    : "";

  const runs = useAutoRefresh(
    () =>
      tab === "review"
        ? api.runs({ review_queue: true, q })
        : api.runs({
            q,
            decision: (filters.decision || undefined) as Decision | undefined,
            flag: (filters.flag || undefined) as Flag | undefined,
            vendor_id: filters.vendor_id || undefined,
            date_from: filters.date_from || undefined,
            date_to: filters.date_to || undefined,
          }),
    [tab, q, filters, pulse],
    { fast },
  );
  const pos = useAutoRefresh(() => api.pos(), [pulse], { fast });
  const vendors = useAutoRefresh(() => api.vendors(), []);

  const [review, setReview] = useState<{ run: RunSummary; action: ReviewAction } | null>(null);
  const [newPO, setNewPO] = useState(false);
  const [createdPO, setCreatedPO] = useState<string | null>(null);

  const update = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };

  const refreshAll = () => {
    void stats.refresh();
    void runs.refresh();
    void pos.refresh();
  };

  const filtered = Object.values(filters).some(Boolean) || q !== "";
  const list = runs.data?.items ?? [];

  return (
    <div className="mx-auto max-w-[1440px] space-y-4 px-4 py-5 sm:px-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)] lg:items-center">
        <div>
          <h1 className="text-lg font-semibold text-ink">Accounts payable</h1>
          <p className="mt-0.5 text-sm text-ink-3">
            Drop in a vendor invoice and Tally checks it against your vendors and purchase orders, catches duplicates
            and risky bank changes, and tells your team exactly what to do next.
          </p>
          {/* Always visible, so raising a PO does not depend on finding the Purchase orders tab first. */}
          <Button
            variant="neutral"
            icon={Plus}
            className="mt-3"
            onClick={() => {
              update({ tab: "pos" });
              setNewPO(true);
            }}
          >
            New purchase order
          </Button>
        </div>
        <Dropzone compact />
      </div>

      <KpiStrip stats={current} />

      <Card className="overflow-hidden">
        <div className="px-4 pt-1">
          <Tabs<TabKey>
            active={tab}
            onChange={(key) => update({ tab: key === "all" ? "" : key })}
            items={[
              { key: "all", label: "All runs", icon: LayoutList, count: current?.runs_total },
              { key: "review", label: "Review queue", icon: Inbox, count: current?.review_queue, attention: true },
              { key: "pos", label: "Purchase orders", icon: Receipt, count: pos.data?.length },
            ]}
          />
        </div>

        {tab === "all" && (
          <div className="border-b border-line px-4 py-3">
            <FilterBar
              values={filters}
              vendors={vendors.data ?? []}
              onChange={(next) => update({ ...next } as unknown as Record<string, string>)}
            />
          </div>
        )}
        {tab !== "pos" && q && (
          <div className="flex items-center gap-2 border-b border-line bg-accent-50 px-4 py-2 text-xs text-accent-800">
            Showing results for <span className="num font-semibold">"{q}"</span>
            <button type="button" className="ml-auto font-semibold hover:underline" onClick={() => update({ q: "" })}>
              Clear search
            </button>
          </div>
        )}

        {(runs.error || pos.error) && (
          <p className="border-b border-line bg-reject-50 px-4 py-2 text-sm text-reject-700">Could not load data: {runs.error ?? pos.error}</p>
        )}

        {tab === "pos" && (
          <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
            {createdPO ? (
              <span className="inline-flex items-center gap-1.5 text-sm font-medium text-approve-700">
                <CircleCheck className="size-4" aria-hidden /> {createdPO} created. Invoices quoting it will now match.
              </span>
            ) : (
              <span className="text-sm text-ink-3">Remaining balance on each order, and the invoices billed against it.</span>
            )}
            <Button variant="primary" icon={Plus} className="ml-auto" onClick={() => setNewPO(true)}>
              New purchase order
            </Button>
          </div>
        )}
        {tab === "pos" ? (
          pos.data ? <POTable pos={pos.data} highlight={createdPO} /> : <p className="px-4 py-10 text-center text-sm text-ink-3">Loading purchase orders...</p>
        ) : runs.loading && !runs.data ? (
          <p className="px-4 py-10 text-center text-sm text-ink-3">Loading runs...</p>
        ) : (
          <RunsTable
            runs={list}
            mode={tab === "review" ? "review" : "all"}
            onReview={(run, action) => setReview({ run, action })}
            empty={
              tab === "review"
                ? "Nothing waiting for review."
                : filtered
                  ? "No runs match these filters."
                  : "No invoices processed yet. Drop a PDF above to start."
            }
          />
        )}
        {tab !== "pos" && runs.data && runs.data.total > list.length && (
          <p className="border-t border-line px-4 py-2 text-xs text-ink-3">
            Showing {list.length} of {runs.data.total}
          </p>
        )}
      </Card>

      {newPO && (
        <NewPODialog
          vendors={vendors.data ?? []}
          onClose={() => setNewPO(false)}
          onCreated={(po) => {
            setNewPO(false);
            setCreatedPO(po.po_number);
            void pos.refresh();
          }}
        />
      )}

      {review && (
        <ReviewDialog
          run={review.run}
          action={review.action}
          onClose={() => setReview(null)}
          onDone={() => {
            setReview(null);
            refreshAll();
          }}
        />
      )}
    </div>
  );
}
