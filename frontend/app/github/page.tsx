"use client";

import { useState, useEffect } from "react";
import { Section, Button, Tag, Spinner, EmptyState } from "../components/ui";
import {
  getGitHubStatus,
  connectGitHub,
  disconnectGitHub,
  GitHubStatus,
} from "../lib/api";
import { ExternalLink } from "lucide-react";

const DISCONNECTED: GitHubStatus = {
  connected: false,
  github_username: null,
  scope: null,
  connected_at: null,
};

const STEPS = [
  {
    title: "Attach a file in chat",
    desc: "Upload code, configs, or a zipped project folder in the chat workspace.",
  },
  {
    title: 'Say "push to GitHub"',
    desc: "The agent detects the intent and returns a confirmation card.",
  },
  {
    title: "Confirm and push",
    desc: "Review the repo name, choose private or public, then confirm.",
  },
];

export default function GitHubPage() {
  const [status, setStatus] = useState<GitHubStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  useEffect(() => {
    getGitHubStatus()
      .then(setStatus)
      .catch(() => setStatus(DISCONNECTED))
      .finally(() => setLoading(false));
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const { auth_url } = await connectGitHub();
      // Redirect to GitHub OAuth consent screen
      window.location.href = auth_url;
    } catch (err) {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await disconnectGitHub();
      setStatus(DISCONNECTED);
    } catch { }
    setDisconnecting(false);
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const connected = status?.connected ?? false;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl">GitHub</h1>
        <p className="mt-1.5 text-sm text-ink-tertiary">
          Link your account to push projects directly from the chat.
        </p>
      </header>

      <Section
        title="Connection"
        action={
          connected ? (
            <Tag variant="good">Connected</Tag>
          ) : (
            <Tag variant="outline">Not connected</Tag>
          )
        }
      >
        {connected ? (
          <div className="space-y-5">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-5 border-b border-rule pb-5 sm:grid-cols-3">
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-tertiary">
                  Account
                </dt>
                <dd className="mt-1 flex items-center gap-1.5 text-ink">
                  @{status?.github_username}
                  <a
                    href={`https://github.com/${status?.github_username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Open on GitHub"
                    className="rounded p-0.5 text-ink-tertiary transition-colors hover:text-accent"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-tertiary">
                  Scope
                </dt>
                <dd className="mt-1 text-ink">{status?.scope || "repo"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-tertiary">
                  Connected
                </dt>
                <dd className="mt-1 text-ink">
                  {status?.connected_at ? (
                    <time>
                      {new Date(status.connected_at).toLocaleDateString(
                        undefined,
                        { year: "numeric", month: "short", day: "numeric" }
                      )}
                    </time>
                  ) : (
                    <span className="text-rule-strong">—</span>
                  )}
                </dd>
              </div>
            </dl>

            <Button
              variant="danger"
              onClick={handleDisconnect}
              disabled={disconnecting}
            >
              {disconnecting && <Spinner className="h-3.5 w-3.5" />}
              Disconnect GitHub
            </Button>
          </div>
        ) : (
          <EmptyState
            title="No account linked"
            description="Authorize CareerOS on GitHub to enable chat-triggered pushes. The access token is encrypted at rest."
            action={
              <Button onClick={handleConnect} disabled={connecting}>
                {connecting && <Spinner className="h-3.5 w-3.5" />}
                Connect GitHub account
              </Button>
            }
          />
        )}
      </Section>

      <Section title="How chat-triggered push works">
        <ol className="divide-y divide-rule border-y border-rule">
          {STEPS.map((item, i) => (
            <li key={item.title} className="flex gap-4 py-4">
              <span
                data-numeric
                className="w-5 shrink-0 font-serif text-lg leading-6 text-ink-tertiary"
              >
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="text-ink">{item.title}</p>
                <p className="mt-0.5 text-sm text-ink-tertiary">{item.desc}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}
