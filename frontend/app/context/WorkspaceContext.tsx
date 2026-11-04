"use client";
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { API_BASE } from "../lib/api";

type Workspace = { id: string; email: string; mode: string };
const Context = createContext<{ user: Workspace | null; loading: boolean; error: string; reload: () => void }>({ user: null, loading: true, error: "", reload: () => {} });

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/workspace`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Workspace is unavailable.");
      setUser(data); setError("");
    } catch (e: any) { setError(e.message || "Start the CareerOS backend to open your workspace."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  return <Context.Provider value={{ user, loading, error, reload }}>{children}</Context.Provider>;
}

export function useWorkspace() { return useContext(Context); }
