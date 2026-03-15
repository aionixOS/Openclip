"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getProjects, deleteProject, createProject, getApiBaseUrl } from "@/lib/api";
import { Project } from "@/lib/types";

function getYouTubeThumbnail(url: string): string | null {
    const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&?/]+)/);
    return match ? `https://img.youtube.com/vi/${match[1]}/hqdefault.jpg` : null;
}

function getYouTubeId(url: string): string | null {
    const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&?/]+)/);
    return match ? match[1] : null;
}

function formatTimeAgo(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime();
    const hours = Math.floor(diff / 3600000);
    if (hours < 1) return "just now";
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

function StatusBadge({ status }: { status: Project["status"] }) {
    const cfg: Record<string, { label: string; cls: string; pulse?: boolean }> = {
        done: { label: "Published", cls: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" },
        error: { label: "Error", cls: "bg-red-500/20 text-red-400 border border-red-500/30" },
        pending: { label: "Pending", cls: "bg-slate-500/20 text-slate-400 border border-slate-500/30" },
        downloading: { label: "Downloading", cls: "bg-blue-500/20 text-blue-400 border border-blue-500/30", pulse: true },
        transcribing: { label: "Transcribing", cls: "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30", pulse: true },
        analyzing: { label: "Analyzing", cls: "bg-violet-500/20 text-violet-400 border border-violet-500/30", pulse: true },
        processing: { label: "Rendering", cls: "bg-amber-500/20 text-amber-400 border border-amber-500/30", pulse: true },
    };
    const c = cfg[status] || cfg.pending;
    return (
        <span className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-wider backdrop-blur-md ${c.cls}`}>
            {c.pulse && <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />}
            {c.label}
        </span>
    );
}

export default function Dashboard() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const searchQuery = searchParams.get("q") || "";
    const [projects, setProjects] = useState<Project[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<"all" | "processing" | "done" | "error">("all");
    const [urlInput, setUrlInput] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const urlRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        getProjects()
            .then(setProjects)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, []);

    const handleDelete = async (e: React.MouseEvent, id: string) => {
        e.preventDefault();
        e.stopPropagation();
        await deleteProject(id).catch(console.error);
        setProjects(prev => prev.filter(p => p.id !== id));
    };

    const handleQuickCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!urlInput.trim() || submitting) return;
        setSubmitting(true);
        try {
            const { project_id } = await createProject(urlInput.trim());
            router.push(`/project/${project_id}`);
        } catch {
            setSubmitting(false);
        }
    };

    const handlePaste = async () => {
        try {
            const text = await navigator.clipboard.readText();
            setUrlInput(text);
            urlRef.current?.focus();
        } catch { /* ignore */ }
    };

    const filtered = projects.filter(p => {
        if (filter === "done" && p.status !== "done") return false;
        if (filter === "error" && p.status !== "error") return false;
        if (filter === "processing" && ["done", "error"].includes(p.status)) return false;
        if (searchQuery) {
            const q = searchQuery.toLowerCase();
            const title = (p.title || "").toLowerCase();
            const url = (p.youtube_url || "").toLowerCase();
            if (!title.includes(q) && !url.includes(q)) return false;
        }
        return true;
    });

    return (
        <div className="mx-auto w-full max-w-7xl px-6 lg:px-20 py-10">

            {/* Hero Banner */}
            <section className="relative mb-16 overflow-hidden rounded-3xl">
                <video
                    autoPlay
                    muted
                    loop
                    playsInline
                    className="absolute inset-0 w-full h-full object-cover"
                    style={{ transform: "scaleX(1.05)" }}
                >
                    <source src="/hero-bg.mp4" type="video/mp4" />
                </video>
                <div className="absolute inset-0 bg-black/75" />
                <div className="absolute inset-0 bg-gradient-to-r from-black/60 via-transparent to-black/40" />
                <div className="relative flex min-h-[360px] items-center p-8 lg:p-16">
                    {/* Text content */}
                    <div className="flex-1 max-w-xl">
                        <span className="mb-4 inline-block rounded-full bg-primary/20 border border-primary/30 px-4 py-1 text-xs font-bold uppercase tracking-widest text-primary">
                            AI Powered Editing
                        </span>
                        <h1 className="mb-5 text-4xl font-bold leading-[1.1] tracking-tight text-white lg:text-5xl">
                            Turn any YouTube video into{" "}
                            <span className="text-gradient">viral clips</span>
                        </h1>
                        <p className="mb-8 text-base text-slate-300 max-w-lg">
                            Automatically extract highlights, add captions, and resize for TikTok, Reels, and Shorts.
                        </p>
                        <div className="flex flex-wrap items-center gap-3 w-full">
                            <Link
                                href="/create"
                                className="flex items-center gap-2 rounded-xl bg-primary px-6 py-3.5 text-sm font-bold text-white glow-primary hover:bg-primary/90 transition-all flex-shrink-0"
                            >
                                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
                                Create New Project
                            </Link>
                            <form onSubmit={handleQuickCreate} className="flex flex-1 min-w-[280px] items-center gap-2 rounded-xl bg-black/50 px-4 py-2.5 border border-white/20 focus-within:border-primary/50 transition-all h-[50px]">
                                <svg className="h-4 w-4 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                                <input
                                    ref={urlRef}
                                    value={urlInput}
                                    onChange={e => setUrlInput(e.target.value)}
                                    className="flex-1 bg-transparent border-none text-sm text-white placeholder-slate-400 focus:ring-0 focus:outline-none p-0"
                                    placeholder="Paste YouTube link..."
                                    type="text"
                                />
                                <button
                                    type="button"
                                    onClick={handlePaste}
                                    className="rounded-lg bg-primary/30 px-3 py-1.5 text-xs font-bold text-primary hover:bg-primary/50 transition-colors uppercase tracking-wider"
                                >
                                    Paste
                                </button>
                            </form>
                        </div>
                    </div>

                    {/* Hero character */}
                    <div className="hidden lg:absolute lg:block right-0 top-0 bottom-0 w-[38%] pointer-events-none overflow-hidden" style={{ position: "absolute" }}>
                        <img
                            src="/hero-character.png"
                            alt="OpenClip mascot"
                            className="absolute bottom-0 right-0 w-full h-auto select-none"
                            style={{ maxHeight: "115%", objectFit: "contain", objectPosition: "bottom right" }}
                        />
                    </div>
                </div>
            </section>

            {/* Filter Bar */}
            <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
                <div className="flex gap-1 p-1 glass rounded-xl">
                    {(["all", "processing", "done", "error"] as const).map(f => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`rounded-lg px-5 py-2 text-sm font-semibold transition-colors capitalize ${
                                filter === f
                                    ? "bg-primary/20 text-primary"
                                    : "text-slate-400 hover:text-white"
                            }`}
                        >
                            {f === "all" ? "All Projects" : f === "processing" ? "In Progress" : f.charAt(0).toUpperCase() + f.slice(1)}
                        </button>
                    ))}
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-sm text-slate-400">Sort by:</span>
                    <select className="rounded-xl border border-white/10 bg-white/5 py-2 pl-4 pr-10 text-sm text-white focus:border-primary focus:outline-none">
                        <option>Recently Edited</option>
                        <option>Date Created</option>
                        <option>Name</option>
                    </select>
                </div>
            </div>

            {/* Project Grid */}
            {loading ? (
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="flex flex-col gap-4">
                            <div className="aspect-video rounded-2xl glass animate-pulse" />
                            <div className="px-1 space-y-2">
                                <div className="h-4 w-3/4 rounded-full bg-white/5 animate-pulse" />
                                <div className="h-3 w-1/2 rounded-full bg-white/5 animate-pulse" />
                            </div>
                        </div>
                    ))}
                </div>
            ) : filtered.length === 0 ? (
                <div className="col-span-full text-center py-24 glass rounded-3xl">
                    <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
                        <svg className="h-8 w-8 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/></svg>
                    </div>
                    <p className="text-slate-300 font-semibold">No projects yet</p>
                    <p className="text-slate-500 text-sm mt-1">Paste a YouTube URL above to get started</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {filtered.map(project => {
                        const thumb = getYouTubeThumbnail(project.youtube_url);
                        const ytId = getYouTubeId(project.youtube_url);
                        const isActive = !["done", "error"].includes(project.status);
                        return (
                            <Link key={project.id} href={`/project/${project.id}`} className="group flex flex-col gap-3">
                                <div className="relative aspect-video overflow-hidden rounded-2xl glass border border-white/5">
                                    {thumb ? (
                                        <img
                                            src={thumb}
                                            alt={project.title || "Project"}
                                            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                                        />
                                    ) : (
                                        <div className="h-full w-full bg-gradient-to-br from-primary/20 to-accent-purple/20 flex items-center justify-center">
                                            <svg className="h-10 w-10 text-primary/40" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                        </div>
                                    )}
                                    <div className="absolute top-3 right-3">
                                        <StatusBadge status={project.status} />
                                    </div>
                                    <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/40 backdrop-blur-sm">
                                        <button className="rounded-full bg-white p-3 text-black shadow-xl">
                                            <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                        </button>
                                    </div>
                                </div>
                                <div className="flex items-start justify-between px-1">
                                    <div className="flex-1 min-w-0 pr-2">
                                        <h3 className="font-bold text-white group-hover:text-primary transition-colors truncate text-sm">
                                            {project.title || (ytId ? `YouTube: ${ytId}` : "Untitled")}
                                        </h3>
                                        <p className="mt-0.5 text-xs text-slate-500">
                                            {formatTimeAgo(project.created_at)}
                                            {project.clip_count ? ` • ${project.clip_count} clips` : ""}
                                        </p>
                                    </div>
                                    <button
                                        onClick={e => handleDelete(e, project.id)}
                                        className="text-slate-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0"
                                    >
                                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                                    </button>
                                </div>
                            </Link>
                        );
                    })}

                    {/* Create new card */}
                    <Link href="/create" className="group flex flex-col gap-3">
                        <div className="relative aspect-video overflow-hidden rounded-2xl border-2 border-dashed border-white/10 hover:border-primary/40 transition-colors flex items-center justify-center">
                            <div className="flex flex-col items-center gap-2 text-slate-600 group-hover:text-primary transition-colors">
                                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/5 group-hover:bg-primary/10 transition-colors">
                                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/></svg>
                                </div>
                                <span className="text-xs font-semibold">Create new project</span>
                            </div>
                        </div>
                    </Link>
                </div>
            )}

            {/* Load More */}
            {filtered.length > 0 && (
                <div className="mt-12 flex justify-center">
                    <button className="rounded-xl glass glass-hover px-8 py-3 text-sm font-semibold text-slate-300 transition-all">
                        Load More Projects
                    </button>
                </div>
            )}

        </div>
    );
}
