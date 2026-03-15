"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getProject, getApiBaseUrl } from "@/lib/api";
import { Project, Clip } from "@/lib/types";

function formatDuration(s: number) {
    const m = Math.floor(s / 60);
    const sec = Math.round(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
}

function getYouTubeId(url: string) {
    const m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&?/]+)/);
    return m ? m[1] : null;
}

const STAGE_LABEL: Record<string, string> = {
    downloading: "Downloading video…",
    transcribing: "Extracting captions…",
    analyzing: "AI analyzing…",
    processing: "Cutting clips…",
    done: "Complete",
    error: "Failed",
};

export default function ProjectPage() {
    const params = useParams();
    const id = params.id as string;

    const [project, setProject] = useState<(Project & { clips: Clip[] }) | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
    const [wsProgress, setWsProgress] = useState<{ stage: string; percent: number; message: string } | null>(null);
    const [logs, setLogs] = useState<string[]>([]);

    useEffect(() => {
        getProject(id)
            .then(data => {
                setProject(data);
                if (data.clips?.length > 0) setSelectedClip(data.clips[0]);
            })
            .catch(err => setError(err instanceof Error ? err.message : "Not found"))
            .finally(() => setLoading(false));
    }, [id]);

    useEffect(() => {
        if (!project || ["done", "error"].includes(project.status)) return;
        const baseUrl = getApiBaseUrl();
        const wsBase = baseUrl.replace(/^https/, "wss").replace(/^http/, "ws");
        const ws = new WebSocket(`${wsBase}/ws/progress/${id}`);
        ws.onmessage = e => {
            try {
                const d = JSON.parse(e.data);
                setWsProgress({ stage: d.stage, percent: d.percent, message: d.message });
                setLogs(prev => [...prev.slice(-49), `[${new Date().toLocaleTimeString()}] ${d.message}`]);
                if (d.stage === "done") { ws.close(); window.location.reload(); }
            } catch { /* ignore */ }
        };
        return () => ws.close();
    }, [project, id]);

    const ytId = project ? getYouTubeId(project.youtube_url) : null;
    const isProcessing = project && !["done", "error"].includes(project.status);
    const pct = wsProgress?.percent ?? 0;
    const clampedPct = Math.min(100, Math.max(0, pct));

    if (loading) {
        return (
            <div className="flex h-[calc(100vh-65px)] items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                    <p className="text-slate-400 text-sm">Loading project…</p>
                </div>
            </div>
        );
    }

    if (error || !project) {
        return (
            <div className="flex h-[calc(100vh-65px)] items-center justify-center flex-col gap-4">
                <p className="text-red-400 font-semibold">{error || "Project not found"}</p>
                <Link href="/" className="text-sm text-primary hover:underline">← Back to Dashboard</Link>
            </div>
        );
    }

    return (
        <div className="flex h-[calc(100vh-65px)] overflow-hidden">
            {/* Left: Video + Meta */}
            <section className="flex-[2] flex flex-col gap-6 overflow-y-auto custom-scrollbar p-8">
                {/* Header */}
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <div className="flex items-center gap-2 mb-1.5">
                            <svg className="h-4 w-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
                            <span className="text-xs font-medium text-slate-500 uppercase tracking-widest">
                                Project / {id.slice(0, 8).toUpperCase()}
                            </span>
                        </div>
                        <h1 className="text-2xl font-bold text-white">{project.title || "Untitled Project"}</h1>
                    </div>
                    <div className="flex gap-3 flex-shrink-0">
                        <Link href="/" className="px-4 py-2 rounded-xl glass glass-hover text-sm font-semibold flex items-center gap-2 text-slate-300">
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
                            Dashboard
                        </Link>
                        {project.clips?.length > 0 && (
                            <button className="px-5 py-2 rounded-xl bg-primary hover:bg-primary/90 text-white text-sm font-bold flex items-center gap-2 glow-primary transition-all">
                                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"/></svg>
                                Export All
                            </button>
                        )}
                    </div>
                </div>

                {/* Video Player */}
                <div className="relative aspect-video rounded-3xl overflow-hidden glass border border-white/5 shadow-2xl bg-black">
                    {selectedClip ? (
                        <video
                            src={`${getApiBaseUrl()}${selectedClip.file_path}`}
                            controls
                            className="w-full h-full object-contain"
                            key={selectedClip.id}
                        />
                    ) : ytId ? (
                        <iframe
                            src={`https://www.youtube.com/embed/${ytId}`}
                            className="w-full h-full"
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowFullScreen
                        />
                    ) : (
                        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
                            {isProcessing ? (
                                <>
                                    <div className="h-10 w-10 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                                    <p className="text-slate-400 text-sm">{STAGE_LABEL[wsProgress?.stage || project.status] || "Processing…"}</p>
                                </>
                            ) : (
                                <div className="flex flex-col items-center gap-2 text-slate-600">
                                    <svg className="h-12 w-12" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                    <p className="text-sm">No video available</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Live Progress (when processing) */}
                {isProcessing && (
                    <div className="glass-card rounded-2xl p-6 space-y-4">
                        <div className="flex justify-between items-center">
                            <div className="flex items-center gap-2">
                                <span className="relative flex h-2 w-2">
                                    <span className="animate-ping absolute h-full w-full rounded-full bg-primary opacity-75" />
                                    <span className="relative rounded-full h-2 w-2 bg-primary" />
                                </span>
                                <p className="text-slate-100 font-semibold text-sm">
                                    {STAGE_LABEL[wsProgress?.stage || project.status] || "Processing…"}
                                </p>
                            </div>
                            <p className="text-primary font-bold">{Math.round(clampedPct)}%</p>
                        </div>
                        <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden">
                            <div
                                className="h-full rounded-full transition-all duration-500"
                                style={{ width: `${clampedPct}%`, background: "linear-gradient(to right, #2e1ded, #8b5cf6)" }}
                            />
                        </div>
                        <div className="bg-[#0a0a0a] rounded-xl p-4 font-mono text-xs space-y-1 max-h-32 overflow-y-auto custom-scrollbar border border-white/5">
                            {logs.length === 0 ? (
                                <span className="text-slate-600 italic">Connecting…</span>
                            ) : (
                                logs.map((log, i) => (
                                    <p key={i} className="text-slate-400">
                                        <span className="text-accent-purple/60">[LOG]</span> {log}
                                    </p>
                                ))
                            )}
                        </div>
                    </div>
                )}

                {/* Video Metadata */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {[
                        { label: "Status", val: project.status.charAt(0).toUpperCase() + project.status.slice(1) },
                        { label: "Clips", val: `${project.clips?.length || 0} generated` },
                        { label: "Source", val: ytId ? `YouTube: ${ytId}` : "Unknown" },
                        { label: "Created", val: new Date(project.created_at).toLocaleDateString() },
                    ].map(({ label, val }) => (
                        <div key={label} className="glass rounded-2xl p-4">
                            <p className="text-xs text-slate-500 mb-1">{label}</p>
                            <p className="text-sm font-bold text-white truncate">{val}</p>
                        </div>
                    ))}
                </div>

                <a href={project.youtube_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-sm text-primary hover:underline">
                    <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                    View original YouTube video
                </a>
            </section>

            {/* Right: Clips Sidebar */}
            <aside className="w-80 flex-shrink-0 border-l border-white/5 flex flex-col">
                <div className="p-5 border-b border-white/5 glass-dark flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <svg className="h-5 w-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3l14 9-14 9V3z"/></svg>
                        <h3 className="font-bold text-white">Generated Clips</h3>
                    </div>
                    {project.clips?.length > 0 && (
                        <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-primary/20 text-primary border border-primary/30">
                            {project.clips.length} TOTAL
                        </span>
                    )}
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-4">
                    {project.clips?.length === 0 && project.status === "done" ? (
                        <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-600">
                            <svg className="h-10 w-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/></svg>
                            <p className="text-sm">No clips generated</p>
                        </div>
                    ) : project.clips?.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-600">
                            <div className="h-6 w-6 rounded-full border-2 border-primary/40 border-t-primary animate-spin" />
                            <p className="text-sm">Processing clips…</p>
                        </div>
                    ) : (
                        project.clips.map((clip, i) => {
                            const isSelected = selectedClip?.id === clip.id;
                            const viralPct = clip.viral_score ? (clip.viral_score / 10) * 100 : 0;
                            return (
                                <div
                                    key={clip.id}
                                    onClick={() => setSelectedClip(clip)}
                                    className={`glass rounded-2xl p-4 flex gap-4 group cursor-pointer transition-all ${
                                        isSelected ? "border border-primary/50 bg-primary/5" : "border border-transparent hover:border-primary/30"
                                    }`}
                                >
                                    <div className="relative w-20 aspect-[9/16] rounded-xl overflow-hidden flex-shrink-0 bg-slate-900">
                                        <div className="absolute inset-0 flex items-center justify-center bg-black/40 group-hover:bg-black/20 transition-opacity">
                                            <svg className={`h-6 w-6 ${isSelected ? "text-primary" : "text-white/60"}`} fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                        </div>
                                        <span className="absolute top-1.5 left-1.5 rounded px-1 py-0.5 text-[9px] font-bold bg-primary text-white">
                                            {formatDuration(clip.duration)}
                                        </span>
                                    </div>
                                    <div className="flex-1 flex flex-col justify-between min-w-0">
                                        <div>
                                            <div className="flex justify-between items-start gap-1">
                                                <h4 className="text-xs font-bold text-white line-clamp-2 leading-snug">
                                                    {clip.title || `Clip ${i + 1}`}
                                                </h4>
                                            </div>
                                            {clip.viral_score !== undefined && (
                                                <div className="mt-2 flex items-center gap-1.5">
                                                    <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500">Viral:</span>
                                                    <div className="flex-1 h-1 bg-white/10 rounded-full">
                                                        <div className="h-full rounded-full bg-gradient-to-r from-primary to-accent-purple" style={{ width: `${viralPct}%` }} />
                                                    </div>
                                                    <span className="text-[9px] font-bold text-primary">{clip.viral_score}/10</span>
                                                </div>
                                            )}
                                        </div>
                                        <div className="flex gap-1.5 mt-3">
                                            <button
                                                onClick={e => { e.stopPropagation(); setSelectedClip(clip); }}
                                                className="flex-1 py-1.5 rounded-lg bg-primary/10 hover:bg-primary text-[9px] font-bold transition-colors text-primary hover:text-white"
                                            >
                                                PREVIEW
                                            </button>
                                            <a
                                                href={`${getApiBaseUrl()}${clip.file_path}`}
                                                download
                                                onClick={e => e.stopPropagation()}
                                                className="flex-1 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-[9px] font-bold transition-colors border border-white/10 text-center"
                                            >
                                                DOWNLOAD
                                            </a>
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>

                {project.status === "done" && (
                    <div className="p-5 border-t border-white/5">
                        <Link
                            href="/create"
                            className="flex items-center justify-center gap-2 w-full py-3.5 rounded-xl bg-primary hover:bg-primary/90 text-white text-sm font-bold glow-primary transition-all"
                        >
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                            Generate More Clips
                        </Link>
                    </div>
                )}
            </aside>
        </div>
    );
}
