"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { useWorkspace } from "../context/WorkspaceContext";
import Link from "next/link";
import TopBar from "./TopBar";
import { TaskProvider } from "../context/TaskContext";

export default function LayoutClient({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, error, reload } = useWorkspace();
  const pathname = usePathname();

  const isBuilderPage = pathname.startsWith("/builder");

  // Resolve the local workspace once on first paint.
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <div className="flex w-[180px] flex-col items-center gap-4">
          <span className="font-serif text-xl tracking-tight text-ink">
            CareerOS
          </span>
          <div
            role="status"
            aria-label="Loading"
            className="h-[2px] w-full overflow-hidden bg-rule"
          >
            <div className="h-full w-1/3 bg-accent animate-rail" />
          </div>
        </div>
      </div>
    );
  }

  // Give an actionable error rather than hiding the entire application.
  if (!user) {
    if (pathname === "/settings") return <main className="mx-auto max-w-3xl px-6 py-12">{children}</main>;
    return <main className="mx-auto max-w-xl px-6 py-20 space-y-4"><h1 className="font-serif text-3xl">Personal workspace</h1><p role="alert">{error}</p><button onClick={reload} className="underline">Retry connection</button><p><Link href="/settings" className="text-accent underline">Select an existing owner in Settings</Link></p></main>;
  }

  // The builder owns the full viewport.
  if (isBuilderPage) {
    return (
      <TaskProvider>
        <div key={pathname} className="h-full w-full animate-fade-in">
          {children}
        </div>
      </TaskProvider>
    );
  }

  return (
    <div className="min-h-screen bg-paper text-ink">
      <TopBar />
      <main className="mx-auto max-w-[1100px] px-6 py-10">
        <TaskProvider>
          <div key={pathname} className="animate-fade-in">
            {children}
          </div>
        </TaskProvider>
      </main>
    </div>
  );
}
