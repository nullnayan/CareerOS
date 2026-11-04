"use client";

import { cn } from "../lib/utils";
import React from "react";

/* ─── Panel ───────────────────────────────────────────────────────────
   A genuinely separable object. Most groupings want <Section> instead. */

export function Panel({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-rule bg-surface", className)}
      {...props}
    />
  );
}

/* ─── Section ─────────────────────────────────────────────────────────
   Heading + hairline + content. No box. This is the default grouping. */

export function Section({
  title,
  description,
  action,
  className,
  children,
  ...props
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
} & Omit<React.HTMLAttributes<HTMLElement>, "title">) {
  return (
    <section className={cn("space-y-4", className)} {...props}>
      {(title || action) && (
        <div className="flex items-end justify-between gap-4 border-b border-rule pb-2">
          <div className="min-w-0">
            {title && (
              <h2 className="text-lg text-ink">{title}</h2>
            )}
            {description && (
              <p className="mt-0.5 text-sm text-ink-tertiary">{description}</p>
            )}
          </div>
          {action && <div className="shrink-0 pb-0.5">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Divider({ className }: { className?: string }) {
  return <hr className={cn("border-rule", className)} />;
}

/* ─── Card (compat) ───────────────────────────────────────────────────
   Kept so unswept pages compile. Flat — no glass, no lift, no glow. */

export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-rule bg-surface text-ink",
        className
      )}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("space-y-1 p-5 pb-3", className)} {...props} />;
}

export function CardTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-lg text-ink", className)} {...props} />;
}

export function CardDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-ink-tertiary", className)} {...props} />;
}

export function CardContent({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5 pt-0", className)} {...props} />;
}

/* ─── Button ──────────────────────────────────────────────────────── */

type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  | "default"
  | "outline"
  | "destructive";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "default" | "lg" | "icon";
}

const BUTTON_VARIANTS: Record<string, string> = {
  primary:
    "bg-accent text-accent-foreground border border-accent hover:bg-accent-hover hover:border-accent-hover",
  secondary:
    "bg-surface text-ink border border-rule-strong hover:bg-sunken",
  ghost:
    "bg-transparent text-ink-secondary border border-transparent hover:bg-sunken hover:text-ink",
  danger:
    "bg-surface text-bad border border-rule-strong hover:bg-bad/[0.06] hover:border-bad/40",
};

export function Button({
  className,
  variant = "primary",
  size = "default",
  ...props
}: ButtonProps) {
  // Legacy names from the old system
  const v =
    variant === "default"
      ? "primary"
      : variant === "outline"
      ? "secondary"
      : variant === "destructive"
      ? "danger"
      : variant;

  return (
    <button
      className={cn(
        "inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded font-medium transition-colors duration-100 disabled:pointer-events-none disabled:opacity-40",
        BUTTON_VARIANTS[v] ?? BUTTON_VARIANTS.primary,
        {
          "h-7 px-2.5 text-xs": size === "sm",
          "h-[34px] px-3.5 text-sm": size === "default",
          "h-10 px-5 text-base": size === "lg",
          "h-[34px] w-[34px] p-0": size === "icon",
        },
        className
      )}
      {...props}
    />
  );
}

/* ─── Tag ─────────────────────────────────────────────────────────────
   Text-weight label. Reads as a word, not a glowing pill. */

interface TagProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?:
    | "default"
    | "good"
    | "warn"
    | "bad"
    | "accent"
    | "outline"
    | "secondary"
    | "success"
    | "destructive";
}

const TAG_VARIANTS: Record<string, string> = {
  default: "bg-sunken text-ink-secondary border-rule",
  good: "bg-good/[0.08] text-good border-good/25",
  warn: "bg-warn/[0.08] text-warn border-warn/25",
  bad: "bg-bad/[0.07] text-bad border-bad/25",
  accent: "bg-accent/[0.08] text-accent border-accent/25",
  outline: "bg-transparent text-ink-secondary border-rule-strong",
};

export function Tag({ className, variant = "default", ...props }: TagProps) {
  const v =
    variant === "success"
      ? "good"
      : variant === "destructive"
      ? "bad"
      : variant === "secondary"
      ? "default"
      : variant;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-medium leading-4",
        TAG_VARIANTS[v] ?? TAG_VARIANTS.default,
        className
      )}
      {...props}
    />
  );
}

/** Legacy alias. */
export const Badge = Tag;

/* ─── Fields ──────────────────────────────────────────────────────── */

const FIELD_BASE =
  "w-full rounded border border-rule-strong bg-surface text-ink placeholder:text-ink-tertiary transition-colors duration-100 hover:border-ink-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-tertiary";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(FIELD_BASE, "h-[34px] px-2.5 text-sm", className)}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        FIELD_BASE,
        "min-h-[120px] resize-y px-2.5 py-2 text-sm leading-relaxed",
        className
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(FIELD_BASE, "h-[34px] px-2 text-sm", className)}
      {...props}
    />
  );
}

export function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "block text-xs font-medium uppercase tracking-wide text-ink-tertiary",
        className
      )}
      {...props}
    />
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && <Label>{label}</Label>}
      {children}
      {error ? (
        <p className="text-xs text-bad">{error}</p>
      ) : hint ? (
        <p className="text-xs text-ink-tertiary">{hint}</p>
      ) : null}
    </div>
  );
}

/* ─── Score ───────────────────────────────────────────────────────────
   A number is a number. Thin arc, one ink colour, no gradient. */

export type Band = { label: string; text: string; stroke: string; bg: string };

export function scoreBand(score: number): Band {
  if (score >= 80)
    return {
      label: "Strong",
      text: "text-good",
      stroke: "rgb(var(--good))",
      bg: "bg-good/[0.07]",
    };
  if (score >= 60)
    return {
      label: "Fair",
      text: "text-warn",
      stroke: "rgb(var(--warn))",
      bg: "bg-warn/[0.07]",
    };
  return {
    label: "Weak",
    text: "text-bad",
    stroke: "rgb(var(--bad))",
    bg: "bg-bad/[0.06]",
  };
}

export function Score({
  score,
  size = 104,
  strokeWidth = 3,
  label,
  className,
}: {
  score: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  className?: string;
}) {
  const band = scoreBand(score);
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (Math.min(100, Math.max(0, score)) / 100) * circumference;

  return (
    <div
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center",
        className
      )}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          stroke="rgb(var(--rule))"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          stroke={band.stroke}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="butt"
          className="transition-[stroke-dashoffset] duration-500 ease-out"
        />
      </svg>
      <div className="absolute flex flex-col items-center leading-none">
        <span
          data-numeric
          className={cn("font-serif", band.text)}
          style={{ fontSize: Math.round(size * 0.34) }}
        >
          {score}
        </span>
        {label && (
          <span className="mt-1 text-xs uppercase tracking-wide text-ink-tertiary">
            {label}
          </span>
        )}
      </div>
    </div>
  );
}

/** Legacy alias — old call sites pass `size` and `label`. */
export const ScoreRing = Score;

export function ScoreBar({
  score,
  className,
}: {
  score: number;
  className?: string;
}) {
  const band = scoreBand(score);
  return (
    <div className={cn("h-1 w-full bg-rule", className)}>
      <div
        className="h-full transition-[width] duration-500 ease-out"
        style={{
          width: `${Math.min(100, Math.max(0, score))}%`,
          background: band.stroke,
        }}
      />
    </div>
  );
}

/* ─── Stat ────────────────────────────────────────────────────────── */

export function Stat({
  label,
  value,
  delta,
  hint,
  className,
  ...props
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  delta?: number | null;
  hint?: React.ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("min-w-0", className)} {...props}>
      <p className="text-xs uppercase tracking-wide text-ink-tertiary">
        {label}
      </p>
      <p
        data-numeric
        className="mt-1.5 font-serif text-[30px] leading-none text-ink"
      >
        {value}
      </p>
      <p className="mt-1.5 text-xs text-ink-tertiary">
        {typeof delta === "number" && delta !== 0 ? (
          <span className={delta > 0 ? "text-good" : "text-bad"}>
            {delta > 0 ? "▲" : "▼"} {Math.abs(delta)}
          </span>
        ) : hint ? (
          hint
        ) : (
          <span className="text-rule-strong">—</span>
        )}
      </p>
    </div>
  );
}

/** Stats separated by hairlines rather than boxed into tiles. */
export function StatRow({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-x-6 gap-y-6 border-y border-rule py-5 md:grid-cols-4 md:divide-x md:divide-rule",
        className
      )}
    >
      {React.Children.map(children, (child, i) => (
        <div className={i > 0 ? "md:pl-6" : undefined}>{child}</div>
      ))}
    </div>
  );
}

/* ─── Table ───────────────────────────────────────────────────────── */

export function Table({
  className,
  ...props
}: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table
        className={cn("w-full border-collapse text-sm", className)}
        {...props}
      />
    </div>
  );
}

export function Th({
  className,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "border-b border-rule-strong px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-ink-tertiary first:pl-0 last:pr-0",
        className
      )}
      {...props}
    />
  );
}

export function Td({
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        "border-b border-rule px-3 py-2.5 align-middle text-ink-secondary first:pl-0 last:pr-0",
        className
      )}
      {...props}
    />
  );
}

export function Tr({
  className,
  ...props
}: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn("group transition-colors hover:bg-sunken", className)}
      {...props}
    />
  );
}

/* ─── Toolbar ─────────────────────────────────────────────────────── */

export function Toolbar({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-wrap items-center gap-2", className)}
      {...props}
    />
  );
}

/** Segmented control — replaces the old glowing tab pills. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: { value: T; label: React.ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex items-center rounded border border-rule-strong bg-surface p-0.5",
        className
      )}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(o.value)}
            className={cn(
              "rounded-sm px-3 py-1 text-sm transition-colors duration-100",
              active
                ? "bg-ink text-paper"
                : "text-ink-secondary hover:text-ink"
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ─── EmptyState ──────────────────────────────────────────────────── */

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center border border-dashed border-rule-strong px-6 py-12 text-center",
        className
      )}
    >
      <p className="font-serif text-lg text-ink">{title}</p>
      {description && (
        <p className="mt-1.5 max-w-sm text-sm text-ink-tertiary">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ─── Feedback ────────────────────────────────────────────────────── */

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-[1.5px] border-rule-strong border-t-ink-secondary",
        className
      )}
    />
  );
}

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse-quiet rounded bg-sunken", className)}
      {...props}
    />
  );
}

export function Note({
  variant = "default",
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  variant?: "default" | "good" | "warn" | "bad";
}) {
  const styles = {
    default: "border-l-rule-strong bg-sunken text-ink-secondary",
    good: "border-l-good bg-good/[0.05] text-ink-secondary",
    warn: "border-l-warn bg-warn/[0.05] text-ink-secondary",
    bad: "border-l-bad bg-bad/[0.05] text-ink-secondary",
  }[variant];

  return (
    <div
      className={cn("border-l-2 px-3.5 py-2.5 text-sm", styles, className)}
      {...props}
    />
  );
}
