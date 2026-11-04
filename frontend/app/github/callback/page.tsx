"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Panel, Button, Spinner, Note } from "../../components/ui";
import { githubCallback } from "../../lib/api";

function GitHubCallbackContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code) {
      setStatus("error");
      setMessage("No authorization code received from GitHub.");
      return;
    }

    githubCallback(code, state || undefined)
      .then((res) => {
        setStatus("success");
        setMessage(`Connected as @${res.github_username}.`);
        // Redirect back to GitHub settings after a short delay
        setTimeout(() => router.push("/github"), 2000);
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err.message || "Failed to connect GitHub account.");
      });
  }, [searchParams, router]);

  return (
    <div className="mx-auto max-w-[420px] py-16">
      <h1 className="text-2xl">Connecting GitHub</h1>
      <Panel className="mt-5 space-y-4 p-6">
        {status === "loading" && (
          <p className="flex items-center gap-2 text-sm text-ink-secondary">
            <Spinner />
            Completing authorization…
          </p>
        )}
        {status === "success" && (
          <>
            <Note variant="good">{message}</Note>
            <p className="text-xs text-ink-tertiary">
              Redirecting to settings…
            </p>
          </>
        )}
        {status === "error" && (
          <>
            <Note variant="bad">{message}</Note>
            <Button variant="secondary" onClick={() => router.push("/github")}>
              Back to GitHub settings
            </Button>
          </>
        )}
      </Panel>
    </div>
  );
}

export default function GitHubCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[60vh] items-center justify-center">
          <Spinner />
        </div>
      }
    >
      <GitHubCallbackContent />
    </Suspense>
  );
}
