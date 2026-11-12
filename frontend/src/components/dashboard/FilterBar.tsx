import { FilterX } from "lucide-react";
import { DECISION_LABELS, FLAG_LABELS } from "../../lib/format";
import type { Vendor } from "../../lib/types";
import { Button, cx } from "../ui/primitives";

export interface FilterValues {
  decision: string;
  flag: string;
  vendor_id: string;
  date_from: string;
  date_to: string;
}

export const EMPTY_FILTERS: FilterValues = { decision: "", flag: "", vendor_id: "", date_from: "", date_to: "" };

const control =
  "h-8 rounded-control border border-line bg-surface px-2 text-sm text-ink focus:border-accent-500 focus:shadow-focus focus:outline-none";

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cx("flex min-w-0 flex-col gap-1", className)}>
      <span className="text-label uppercase text-ink-3">{label}</span>
      {children}
    </label>
  );
}

export function FilterBar({
  values,
  vendors,
  onChange,
}: {
  values: FilterValues;
  vendors: Vendor[];
  onChange: (next: FilterValues) => void;
}) {
  const set = (key: keyof FilterValues) => (e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) =>
    onChange({ ...values, [key]: e.target.value });
  const active = Object.values(values).some(Boolean);
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:flex lg:flex-wrap lg:items-end">
      <Field label="Decision">
        <select className={control} value={values.decision} onChange={set("decision")}>
          <option value="">All decisions</option>
          {Object.entries(DECISION_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Flag">
        <select className={control} value={values.flag} onChange={set("flag")}>
          <option value="">Any flag</option>
          {Object.entries(FLAG_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Vendor" className="lg:w-56">
        <select className={control} value={values.vendor_id} onChange={set("vendor_id")}>
          <option value="">All vendors</option>
          {vendors.map((v) => (
            <option key={v.vendor_id} value={v.vendor_id}>
              {v.legal_name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Processed from">
        <input type="date" className={control} value={values.date_from} onChange={set("date_from")} />
      </Field>
      <Field label="Processed to">
        <input type="date" className={control} value={values.date_to} onChange={set("date_to")} />
      </Field>
      {active && (
        <Button variant="ghost" icon={FilterX} onClick={() => onChange(EMPTY_FILTERS)} className="self-end">
          Clear
        </Button>
      )}
    </div>
  );
}
