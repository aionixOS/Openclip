"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Copy, Download, Loader2, RotateCcw, Wrench, X } from "lucide-react";
import { getInstallProgress, getSystemHealth, startSystemInstall } from "@/lib/api";
import { InstallJob, InstallStep, SystemHealth, SystemTool } from "@/lib/types";

/* ------------------------------------------------------------------ */
/* Progress ring                                                       */
/* ------------------------------------------------------------------ */

function ProgressRing({ percent, state }: { percent: number; state: "running" | "done" | "error" }) {
    const size = 72;
    const stroke = 6;
    const r = (size - stroke) / 2;
    const circumference = 2 * Math.PI * r;
    const clamped = Math.min(100, Math.max(0, percent));
    const offset = circumference * (1 - clamped / 100);

    const color =
        state === "done" ? "#3ecf8e" : state === "error" ? "#f87171" : "url(#setup-ring-gradient)";

    return (
        <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90">
                <defs>
                    <linearGradient id="setup-ring-gradient" x1="0" y1="0" x2="1" y2="1">
                        <stop offset="0%" stopColor="#2e1ded" />
                        <stop offset="100%" stopColor="#8b5cf6" />
                    </linearGradient>
                </defs>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={r}
                    fill="none"
                    stroke={color}
                    strokeWidth={stroke}
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    style={{
                        transition: "stroke-dashoffset 0.6s ease-out, stroke 0.3s",
                        filter: state === "running" ? "drop-shadow(0 0 6px rgba(46,29,237,0.6))" : undefined,
                    }}
                />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
                {state === "done" ? (
                    <Check className="h-7 w-7 text-[#3ecf8e]" strokeWidth={3} />
                ) : state === "error" ? (
                    <X className="h-7 w-7 text-red-400" strokeWidth={3} />
                ) : (
                    <span className="text-sm font-bold text-white tabular-nums">{Math.round(clamped)}%</span>
                )}
            </div>
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Small pieces                                                        */
/* ------------------------------------------------------------------ */

function ToolChip({ tool }: { tool: SystemTool }) {
    return (
        <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-bold ${
                tool.ok
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                    : "border-amber-500/25 bg-amber-500/10 text-amber-400"
            }`}
            title={tool.description}
        >
            {tool.ok ? <Check className="h-3 w-3" strokeWidth={3} /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
            {tool.name}
            {!tool.ok && <span className="font-medium opacity-70">missing</span>}
        </span>
    );
}

function StepRow({ step }: { step: InstallStep }) {
    return (
        <div className="flex items-center gap-2.5 text-xs">
            <span className="flex h-4 w-4 items-center justify-center">
                {step.state === "done" && <Check className="h-3.5 w-3.5 text-[#3ecf8e]" strokeWidth={3} />}
                {step.state === "running" && <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-purple" />}
                {step.state === "error" && <X className="h-3.5 w-3.5 text-red-400" strokeWidth={3} />}
                {step.state === "pending" && <span className="h-1.5 w-1.5 rounded-full bg-slate-600" />}
            </span>
            <span className={step.state === "pending" ? "text-slate-500" : "text-slate-200 font-semibold"}>{step.name}</span>
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Main card                                                           */
/* ------------------------------------------------------------------ */

const POLL_MS = 700;

export function SystemSetup({ className = "" }: { className?: string }) {
    const [health, setHealth] = useState<SystemHealth | null>(null);
    const [job, setJob] = useState<InstallJob | null>(null);
    const [requestError, setRequestError] = useState<string | null>(null);
    const [showDetails, setShowDetails] = useState(false);
    const [copied, setCopied] = useState<string | null>(null);
    const [dismissed, setDismissed] = useState(false);
    const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const stopPolling = () => {
        if (pollRef.current) clearTimeout(pollRef.current);
        pollRef.current = null;
    };

    const poll = useCallback(() => {
        stopPolling();
        const tick = async () => {
            try {
                const next = await getInstallProgress();
                if (next.state === "idle") {
                    // The backend restarted mid-install and lost the job
                    setJob(prev => ({
                        ...(prev ?? next),
                        state: "error",
                        error: "The backend restarted during the install. Click Try again.",
                    }));
                    setHealth(await getSystemHealth());
                    return;
                }
                setJob(next);
                if (next.state === "running") {
                    pollRef.current = setTimeout(tick, POLL_MS);
                } else {
                    setHealth(await getSystemHealth());
                }
            } catch {
                // Backend briefly unreachable (e.g. reloading) — keep trying
                pollRef.current = setTimeout(tick, POLL_MS * 3);
            }
        };
        tick();
    }, []);

    useEffect(() => {
        getSystemHealth().then(h => {
            setHealth(h);
            if (h?.install.state === "running") {
                // Page was reloaded mid-install: pick the progress back up
                setJob(h.install);
                poll();
            }
        });
        return stopPolling;
    }, [poll]);

    // Hide the success state a few seconds after everything is installed
    useEffect(() => {
        if (job?.state === "done") {
            const t = setTimeout(() => setDismissed(true), 4000);
            return () => clearTimeout(t);
        }
    }, [job?.state]);

    const handleInstall = async () => {
        setRequestError(null);
        setShowDetails(false);
        setDismissed(false);
        try {
            const started = await startSystemInstall();
            setJob(started);
            poll();
        } catch {
            setRequestError("Couldn't start the installer. Is the backend running?");
        }
    };

    const copy = async (text: string) => {
        try {
            await navigator.clipboard.writeText(text);
            setCopied(text);
            setTimeout(() => setCopied(null), 1500);
        } catch { /* ignore */ }
    };

    if (!health || dismissed) return null;

    const phase: "missing" | "running" | "done" | "error" =
        job?.state === "running" ? "running"
        : job?.state === "done" ? "done"
        : job?.state === "error" ? "error"
        : "missing";

    if (phase === "missing" && health.ready) return null;

    const missing = health.tools.filter(t => !t.ok);
    const installable = missing.filter(t => t.can_install);
    const manualOnly = missing.filter(t => !t.can_install);
    const currentStep = job?.steps.find(s => s.state === "running");

    const tone =
        phase === "done" ? "border-emerald-500/20 bg-emerald-500/[0.06]"
        : phase === "error" ? "border-red-500/20 bg-red-500/[0.06]"
        : "glass-card";

    return (
        <div className={`rounded-2xl border p-5 ${tone} ${className}`} role="status" aria-live="polite">
            {/* ---------- Missing ---------- */}
            {phase === "missing" && (
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-start gap-4">
                        <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-primary/20 border border-primary/30">
                            <Wrench className="h-5 w-5 text-accent-purple" />
                        </div>
                        <div className="min-w-0">
                            <p className="font-bold text-sm text-white">Finish setting up OpenClip</p>
                            <p className="mt-0.5 text-xs text-slate-400">
                                {missing.length === 1 ? "One tool is" : `${missing.length} tools are`} missing.
                                {installable.length > 0 && " One click installs everything — no terminal needed."}
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2">
                                {health.tools.map(t => <ToolChip key={t.id} tool={t} />)}
                            </div>
                            {manualOnly.map(t => (
                                <p key={t.id} className="mt-3 text-xs text-slate-400">
                                    {t.name} can&apos;t be installed automatically here. Run{" "}
                                    <button onClick={() => copy(t.manual)} className="font-mono text-slate-200 underline decoration-dotted underline-offset-2 hover:text-white">
                                        {t.manual}
                                    </button>
                                    {copied === t.manual && <span className="ml-1 text-emerald-400">copied</span>}
                                </p>
                            ))}
                            {requestError && <p className="mt-3 text-xs text-red-400">{requestError}</p>}
                        </div>
                    </div>
                    {installable.length > 0 && (
                        <button
                            onClick={handleInstall}
                            className="flex flex-shrink-0 items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3 text-sm font-bold text-white glow-primary hover:bg-primary/90 transition-all"
                        >
                            <Download className="h-4 w-4" />
                            Install
                        </button>
                    )}
                </div>
            )}

            {/* ---------- Running / done / error ---------- */}
            {phase !== "missing" && job && (
                <div className="flex items-center gap-5">
                    <ProgressRing percent={phase === "done" ? 100 : job.percent} state={phase} />
                    <div className="min-w-0 flex-1">
                        <p className="font-bold text-sm text-white">
                            {phase === "running" && (currentStep ? `Installing ${currentStep.name}…` : "Getting ready…")}
                            {phase === "done" && "All set! OpenClip is ready to go."}
                            {phase === "error" && "Installation didn't finish"}
                        </p>
                        <p className={`mt-0.5 truncate text-xs ${phase === "error" ? "text-red-400" : "text-slate-400"}`}>
                            {phase === "running" && (job.message || "Working…")}
                            {phase === "done" && "Everything OpenClip needs is installed."}
                            {phase === "error" && (job.error || "Something went wrong.")}
                        </p>
                        {job.steps.length > 0 && phase !== "done" && (
                            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
                                {job.steps.map(s => <StepRow key={s.id} step={s} />)}
                            </div>
                        )}
                    </div>
                    {phase === "error" && (
                        <button
                            onClick={handleInstall}
                            className="flex flex-shrink-0 items-center gap-2 rounded-xl bg-white/5 border border-white/10 px-4 py-2.5 text-xs font-bold text-slate-200 hover:bg-white/10 transition-all"
                        >
                            <RotateCcw className="h-3.5 w-3.5" />
                            Try again
                        </button>
                    )}
                </div>
            )}

            {/* ---------- Error details ---------- */}
            {phase === "error" && job && (
                <div className="mt-4 border-t border-white/5 pt-3">
                    <button
                        onClick={() => setShowDetails(v => !v)}
                        className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-slate-500 hover:text-slate-300"
                    >
                        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showDetails ? "rotate-180" : ""}`} />
                        Details
                    </button>
                    {showDetails && (
                        <div className="mt-3 space-y-3">
                            <div className="text-xs text-slate-400">
                                You can also install it yourself:
                                {missing.map(t => (
                                    <div key={t.id} className="mt-1.5 flex items-center gap-2">
                                        <code className="rounded-lg bg-black/40 border border-white/5 px-2.5 py-1 font-mono text-slate-200">{t.manual}</code>
                                        <button onClick={() => copy(t.manual)} className="text-slate-500 hover:text-white" aria-label={`Copy ${t.manual}`}>
                                            {copied === t.manual ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                                        </button>
                                    </div>
                                ))}
                            </div>
                            {job.log.length > 0 && (
                                <pre className="max-h-40 overflow-y-auto custom-scrollbar rounded-xl bg-[#0a0a0a] border border-white/5 p-3 font-mono text-[11px] leading-relaxed text-slate-500 whitespace-pre-wrap">
                                    {job.log.join("\n")}
                                </pre>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
