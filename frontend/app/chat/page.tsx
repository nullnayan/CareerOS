"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import {
  Card, CardContent, CardHeader, CardTitle,
  Button, Spinner, Badge,
} from "../components/ui";
import {
  sendChatMessage,
  getChatHistory,
  createChatSession,
  ChatMessageItem,
  ChatSource,
  pushToGitHub,
} from "../lib/api";
import {
  Send,
  MessageSquare,
  Bot,
  User,
  Sparkles,
  FileText,
  Plus,
  ChevronDown,
  Paperclip,
  X,
  Globe,
  Lock,
  Check,
  AlertTriangle,
  ExternalLink,
  Download,
  Square,
} from "lucide-react";
import { GithubIcon } from "../components/GithubIcon";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[];
  pushEvent?: {
    id: string;
    repo_name: string;
    description?: string;
    files?: { path: string; content: string }[];
    status: 'pending' | 'pushing' | 'success' | 'error';
    error_message?: string;
  };
  tailorEvent?: {
    resume_id: string;
    original_resume_id: string | null;
    changes_summary: string;
  };
  isLoading?: boolean;
}

function PushEventCard({
  pushEvent,
  onSuccess,
}: {
  pushEvent: {
    id: string;
    repo_name: string;
    description?: string;
    files?: { path: string; content: string }[];
    status: 'pending' | 'pushing' | 'success' | 'error';
    repo_url?: string;
    error_message?: string;
  };
  onSuccess: (repoUrl: string) => void;
}) {
  const [repoName, setRepoName] = useState(pushEvent.repo_name);
  const [desc, setDesc] = useState(pushEvent.description || "");
  const [isPrivate, setIsPrivate] = useState(false);
  const [status, setStatus] = useState<'pending' | 'pushing' | 'success' | 'error'>(pushEvent.status);
  const [repoUrl, setRepoUrl] = useState(pushEvent.repo_url || "");
  const [errorMsg, setErrorMsg] = useState(pushEvent.error_message || "");

  const handleConfirm = async () => {
    setStatus('pushing');
    try {
      const res = await pushToGitHub(
        repoName,
        pushEvent.files || [],
        desc,
        isPrivate,
        pushEvent.id
      );
      if (res.status === 'success' && res.repo_url) {
        setStatus('success');
        setRepoUrl(res.repo_url);
        onSuccess(res.repo_url);
      } else {
        setStatus('error');
        setErrorMsg(res.error || 'Failed to push repository.');
      }
    } catch (err: any) {
      setStatus('error');
      setErrorMsg(err.message || 'Network error.');
    }
  };

  return (
    <div className="mt-4 rounded-lg border border-border bg-card/60 p-4 space-y-4 max-w-md shadow-sm">
      <div className="flex items-center gap-2 border-b border-border/50 pb-2">
        <GithubIcon className="h-4 w-4 text-muted-foreground" />
        <span className="font-semibold text-xs text-muted-foreground uppercase tracking-wider">GitHub Push Details</span>
      </div>

      {status === 'pending' && (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground font-medium block mb-1">Repository Name</label>
            <input
              type="text"
              value={repoName}
              onChange={(e) => setRepoName(e.target.value)}
              className="w-full rounded-md border border-input bg-background/50 px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground font-medium block mb-1">Description (Optional)</label>
            <input
              type="text"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="e.g. Portfolio project built with React"
              className="w-full rounded-md border border-input bg-background/50 px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id={`private-${pushEvent.id}`}
              checked={isPrivate}
              onChange={(e) => setIsPrivate(e.target.checked)}
              className="rounded border-input text-primary focus:ring-primary h-3.5 w-3.5"
            />
            <label htmlFor={`private-${pushEvent.id}`} className="text-xs text-muted-foreground font-medium flex items-center gap-1 select-none cursor-pointer">
              {isPrivate ? <Lock className="h-3 w-3" /> : <Globe className="h-3 w-3" />}
              Private Repository
            </label>
          </div>
          {pushEvent.files && pushEvent.files.length > 0 && (
            <div className="rounded bg-accent/30 p-2 text-[10px] text-muted-foreground font-mono truncate">
              Files: {pushEvent.files.map(f => f.path).join(', ')}
            </div>
          )}
          <Button size="sm" className="w-full text-xs h-8" onClick={handleConfirm}>
            Confirm &amp; Push to GitHub
          </Button>
        </div>
      )}

      {status === 'pushing' && (
        <div className="flex flex-col items-center justify-center py-6 space-y-2">
          <Spinner className="h-6 w-6 text-primary" />
          <p className="text-xs text-muted-foreground">Creating repository and pushing files...</p>
        </div>
      )}

      {status === 'success' && (
        <div className="space-y-3 text-center py-2 animate-fade-in">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10 mx-auto">
            <Check className="h-6 w-6 text-emerald-400" />
          </div>
          <div>
            <p className="text-xs font-semibold text-emerald-400">Successfully Pushed!</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">Your project is live on GitHub.</p>
          </div>
          <a
            href={repoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline mt-2 font-medium"
          >
            Open Repository <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>
      )}

      {status === 'error' && (
        <div className="space-y-3 animate-fade-in">
          <div className="flex items-center gap-2 text-red-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <p className="text-xs font-semibold">Push Failed</p>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed bg-red-500/5 border border-red-500/10 rounded p-2.5">
            {errorMsg}
          </p>
          <Button variant="outline" size="sm" className="w-full text-xs h-8" onClick={() => setStatus('pending')}>
            Try Again
          </Button>
        </div>
      )}
    </div>
  );
}

function TailoredResumeCard({
  tailorEvent,
}: {
  tailorEvent: {
    resume_id: string;
    original_resume_id: string | null;
    changes_summary: string;
  };
}) {
  return (
    <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-3 max-w-md shadow-sm">
      <div className="flex items-center gap-2 border-b border-emerald-500/20 pb-2">
        <Sparkles className="h-4 w-4 text-emerald-400" />
        <span className="font-semibold text-xs text-emerald-400 uppercase tracking-wider">Resume Tailored</span>
      </div>
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground leading-relaxed">
          {tailorEvent.changes_summary}
        </p>
      </div>
      <a
        href={`/resume/preview/${tailorEvent.resume_id}`}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-center gap-2 w-full rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium py-2 px-4 transition-colors"
      >
        <Download className="h-3.5 w-3.5" />
        Preview & Download PDF
      </a>
    </div>
  );
}

export default function ChatPage() {
  const searchParams = useSearchParams();
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showSources, setShowSources] = useState<string | null>(null);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const typingIntervalRef = useRef<any>(null);

  // Initialize input from URL parameter if present (e.g. from dashboard)
  useEffect(() => {
    const preprompt = searchParams.get("preprompt");
    if (preprompt) {
      setInput(preprompt);
      // Give focus to textarea
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          // Adjust height
          inputRef.current.style.height = "auto";
          inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 160) + "px";
        }
      }, 100);
    }
  }, [searchParams]);

  // Auto-scroll to bottom when messages change
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Create a session on mount
  useEffect(() => {
    createChatSession()
      .then((res) => setSessionId(res.session_id))
      .catch(() => {});
  }, []);

  const handleNewSession = async () => {
    try {
      const res = await createChatSession();
      setSessionId(res.session_id);
      setMessages([]);
    } catch { }
  };

  const handleStop = () => {
    if (typingIntervalRef.current) {
      clearInterval(typingIntervalRef.current);
      typingIntervalRef.current = null;
    }
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    
    setMessages((prev) =>
      prev.map((m) =>
        m.isLoading || m.content === "" // also handle stopping during typewriter typing
          ? {
              ...m,
              content: m.content ? m.content + " (Response stopped.)" : "Response stopped.",
              isLoading: false,
            }
          : m
      )
    );
    setSending(false);
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed && !attachment || sending) return;

    const attachmentLabel = attachment
      ? `\n\n[Attached ${attachment.type.startsWith("image/") ? "Image" : "Document"}: ${attachment.name}]`
      : "";

    const userMsg: DisplayMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed + attachmentLabel,
    };

    const loadingMsg: DisplayMessage = {
      id: `loading-${Date.now()}`,
      role: "assistant",
      content: "",
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setInput("");
    setSending(true);

    // Auto-resize textarea back
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    // Create new abort controller
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await sendChatMessage(
        trimmed,
        sessionId || undefined,
        attachment || undefined,
        controller.signal
      );

      if (!sessionId) {
        setSessionId(res.session_id);
      }
      
      setAttachment(null);

      // 1. First set the message structure with empty content to remove the loading state
      setMessages((prev) =>
        prev.map((m) =>
          m.isLoading
            ? {
              id: res.assistant_message_id,
              role: "assistant" as const,
              content: "",
              sources: res.sources,
              pushEvent: res.push_event
                ? {
                  id: res.push_event.id,
                  repo_name: res.push_event.repo_name,
                  description: res.push_event.description || "",
                  files: res.push_event.files || [],
                  status: 'pending' as const,
                }
                : undefined,
              tailorEvent: res.tailor_event
                ? {
                  resume_id: res.tailor_event.resume_id,
                  original_resume_id: res.tailor_event.original_resume_id,
                  changes_summary: res.tailor_event.changes_summary,
                }
                : undefined,
              isLoading: false,
            }
            : m
        )
      );

      // 2. Animate the typing effect character-by-character (or word-by-word)
      let currentIdx = 0;
      const totalLength = res.answer.length;
      // Adjust typing speed based on length so users aren't waiting forever for huge responses
      const charsPerTick = Math.max(3, Math.ceil(totalLength / 80)); 
      
      typingIntervalRef.current = setInterval(() => {
        currentIdx += charsPerTick;
        if (currentIdx >= totalLength) {
          if (typingIntervalRef.current) {
            clearInterval(typingIntervalRef.current);
            typingIntervalRef.current = null;
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === res.assistant_message_id
                ? { ...m, content: res.answer }
                : m
            )
          );
          setSending(false);
        } else {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === res.assistant_message_id
                ? { ...m, content: res.answer.substring(0, currentIdx) }
                : m
            )
          );
        }
      }, 15);

    } catch (err: any) {
      if (err.name === "AbortError" || (err.message && err.message.toLowerCase().includes("abort"))) {
        // Stopped by user, handleStop has already processed state
        return;
      }
      setMessages((prev) =>
        prev.map((m) =>
          m.isLoading
            ? {
              ...m,
              content:
                "Sorry, I couldn't process that. " +
                (err.message || "Please try again."),
              isLoading: false,
            }
            : m
        )
      );
      setSending(false);
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-resize
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setAttachment(e.target.files[0]);
    }
  };

  const triggerFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setAttachment(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="gradient-text">AI Chat</span>
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Ask questions about your career data — grounded in your actual resumes and skills.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleNewSession}>
          <Plus className="h-4 w-4 mr-2" />
          New Chat
        </Button>
      </div>

      {/* Chat area */}
      <Card 
        className={`flex-1 flex flex-col overflow-hidden relative transition-colors duration-200 ${
          isDragging ? "border-primary border-dashed bg-primary/5" : ""
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {isDragging && (
          <div className="absolute inset-0 bg-background/90 backdrop-blur-sm z-50 flex flex-col items-center justify-center border-2 border-dashed border-primary m-2 rounded-xl animate-fade-in pointer-events-none">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 mb-3">
              <Paperclip className="h-6 w-6 text-primary" />
            </div>
            <p className="text-sm font-semibold">Drop your files here</p>
            <p className="text-xs text-muted-foreground mt-1">Supports code files, images, and ZIP archives</p>
          </div>
        )}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Empty state */}
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center space-y-4">
              <div className="relative">
                <div className="absolute inset-0 bg-primary/20 rounded-full blur-xl animate-pulse" />
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 border border-primary/20">
                  <Sparkles className="h-8 w-8 text-primary" />
                </div>
              </div>
              <div>
                <h3 className="text-lg font-semibold">What can I help with?</h3>
                <p className="text-sm text-muted-foreground mt-1 max-w-md">
                  I can answer questions about your resume, skills, experience, and projects.
                  Try asking me something!
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-4 max-w-lg">
                {[
                  "Which of my projects use Docker?",
                  "What skills am I missing for a backend role?",
                  "Summarize my work experience",
                  "What technologies have I used?",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => {
                      setInput(suggestion);
                      inputRef.current?.focus();
                    }}
                    className="text-left text-xs rounded-lg border border-border px-3 py-2.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-all duration-200"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 animate-fade-in ${msg.role === "user" ? "justify-end" : "justify-start"
                }`}
            >
              {msg.role === "assistant" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 border border-primary/20 mt-0.5">
                  <Bot className="h-4 w-4 text-primary" />
                </div>
              )}

              <div
                className={`max-w-[75%] rounded-xl px-4 py-3 text-sm leading-relaxed ${msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-accent/50 border border-border"
                  }`}
              >
                {msg.isLoading ? (
                  <div className="flex items-center gap-2">
                    <Spinner className="h-4 w-4" />
                    <span className="text-muted-foreground">Thinking...</span>
                  </div>
                ) : (
                  <>
                    <div className="whitespace-pre-wrap">{msg.content}</div>

                    {/* Source citations */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-border/50">
                        <button
                          onClick={() =>
                            setShowSources(
                              showSources === msg.id ? null : msg.id
                            )
                          }
                          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                        >
                          <FileText className="h-3 w-3" />
                          {msg.sources.length} source{msg.sources.length !== 1 ? "s" : ""}
                          <ChevronDown
                            className={`h-3 w-3 transition-transform ${showSources === msg.id ? "rotate-180" : ""
                              }`}
                          />
                        </button>

                        {showSources === msg.id && (
                          <div className="mt-2 space-y-2 animate-fade-in">
                            {msg.sources.map((src, i) => (
                              <div
                                key={i}
                                className="rounded-lg bg-background/50 border border-border/50 p-2.5 text-xs"
                              >
                                <div className="flex items-center gap-2 mb-1">
                                  <Badge variant="outline" className="text-[10px] py-0">
                                    {src.source_filename || "resume"}
                                  </Badge>
                                  <span className="text-muted-foreground">
                                    relevance: {(src.score * 100).toFixed(0)}%
                                  </span>
                                </div>
                                <p className="text-muted-foreground leading-relaxed">
                                  {src.chunk_text}
                                </p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    {/* Render GitHub Push Event Card */}
                    {msg.pushEvent && (
                      <PushEventCard
                        pushEvent={msg.pushEvent}
                        onSuccess={(repoUrl) => {
                          console.log("Pushed successfully to:", repoUrl);
                        }}
                      />
                    )}
                    {/* Render Tailored Resume Card */}
                    {msg.tailorEvent && (
                      <TailoredResumeCard tailorEvent={msg.tailorEvent} />
                    )}
                  </>
                )}
              </div>

              {msg.role === "user" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary border border-border mt-0.5">
                  <User className="h-4 w-4 text-muted-foreground" />
                </div>
              )}
            </div>
          ))}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="border-t border-border p-4">
          {/* Attachment Preview Banner */}
          {attachment && (
            <div className="flex items-center justify-between rounded-lg border border-border bg-accent/30 p-2 mb-3 text-xs animate-fade-in">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-primary" />
                <span className="font-medium truncate max-w-[200px]">{attachment.name}</span>
                <span className="text-muted-foreground">({(attachment.size / 1024).toFixed(1)} KB)</span>
              </div>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setAttachment(null)}>
                <X className="h-3 w-3" />
              </Button>
            </div>
          )}

          <div className="flex items-end gap-3">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              className="hidden"
              accept=".pdf,.docx,.txt,.zip,image/*"
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-11 w-11 rounded-xl shrink-0"
              onClick={triggerFileSelect}
              disabled={sending}
            >
              <Paperclip className="h-4 w-4" />
            </Button>

            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={handleTextareaInput}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your career data, or attach files/images..."
                rows={1}
                className="flex w-full rounded-xl border border-input bg-background px-4 py-3 pr-12 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200 resize-none overflow-hidden"
                disabled={sending}
              />
            </div>
            {sending ? (
              <Button
                onClick={handleStop}
                variant="destructive"
                size="icon"
                className="h-11 w-11 rounded-xl shrink-0"
              >
                <Square className="h-4 w-4 fill-white" />
              </Button>
            ) : (
              <Button
                onClick={handleSend}
                disabled={!input.trim() && !attachment}
                size="icon"
                className="h-11 w-11 rounded-xl shrink-0"
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
          <p className="text-[10px] text-muted-foreground mt-2 text-center">
            Answers are grounded in your uploaded career data. Press Enter to send, Shift+Enter for new line.
          </p>
        </div>
      </Card>
    </div>
  );
}
