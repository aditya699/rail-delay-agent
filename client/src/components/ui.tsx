// Small presentational building blocks shared by every feature.

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-zinc-900 text-white hover:bg-zinc-700 disabled:bg-zinc-300 disabled:text-zinc-500",
  secondary: "border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-100 disabled:text-zinc-400",
  ghost: "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 disabled:text-zinc-300",
  danger: "text-red-700 hover:bg-red-50 disabled:text-red-300",
};

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed";

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button type="button" className={`${BUTTON_BASE} ${VARIANTS[variant]} ${className}`} {...props} />;
}

export function Badge({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {children}
    </span>
  );
}

export function Spinner({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-block shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    />
  );
}

export function Panel({
  title,
  children,
  actions,
  className = "",
}: {
  title: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`min-w-0 rounded-lg border border-zinc-200 bg-white ${className}`}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-100 px-4 py-2.5">
        <h2 className="text-sm font-semibold text-zinc-800">{title}</h2>
        {actions}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{children}</h3>;
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return <p className="text-sm text-red-700">{message}</p>;
}

/** A calm notice for expected refusals (e.g. a feature switched off on the server). */
export function Notice({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">{children}</p>;
}

export const inputClass =
  "w-full min-w-0 rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";

export const selectClass =
  "rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";
