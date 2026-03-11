"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, AlertCircle } from "lucide-react";
import { getProject, BASE_URL } from "@/lib/api";
import { Project, Clip } from "@/lib/types";
import { VideoEmbed } from "@/components/project/VideoEmbed";
import { ClipGrid } from "@/components/create/ClipGrid";
import { ProgressBar } from "@/components/create/ProgressBar";

export default function ProjectPage() {
    const params = useParams();
    const router = useRouter();
    const id = params.id as string;

    const [project, setProject] = useState<(Project & { clips: Clip[] }) | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // WebSocket state
    const [wsProgress, setWsProgress] = useState<{ stage: string; percent: number; message: string } | null>(null);
    const [logs, setLogs] = useState<{ time: string; text: string }[]>([]);

    useEffect(() => {
        async function loadProject() {
            try {
                const data = await getProject(id);
                setProject(data);
            } catch (err: unknown) {
                console.error("Failed to load project:", err);
                setError(err instanceof Error ? err.message : "Project not found");
            } finally {
                setLoading(false);
            }
        }
        loadProject();
    }, [id]);

    useEffect(() => {
        if (!project || project.status === "done" || project.status === "error") return;

        const wsUrl = BASE_URL.replace(/^http/, "ws") + `/ws/progress/${id}`;
        const ws = new WebSocket(wsUrl);

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                setWsProgress({
                    stage: data.stage,
                    percent: data.percent,
                    message: data.message
                });

                // Add to logs
                setLogs(prev => [...prev.slice(-19), {
                    time: new Date().toLocaleTimeString(),
                    text: `[${data.stage}] ${data.message} (${Math.round(data.percent)}%)`
                }]);

                // Auto-refresh when complete
                if (data.stage === "done") {
                    ws.close();
                    window.location.reload();
                }
            } catch (err) {
                console.error("Failed to parse WebSocket message", err);
            }
        };

        return () => ws.close();
    }, [project, id]);

    if (loading) {
        return (
            <div className="container mx-auto px-4 py-8 md:px-6 md:py-12 max-w-6xl">
                <div className="flex items-center text-sm text-gray-400 mb-8 opacity-50">
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back to Dashboard
                </div>

                <div className="mb-8">
                    <div className="h-8 w-1/3 bg-gray-800 rounded animate-pulse mb-3"></div>
                    <div className="h-4 w-1/4 bg-gray-800 rounded animate-pulse"></div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-12">
                    <div className="lg:col-span-2 w-full aspect-video rounded-lg border border-[var(--border)] bg-[var(--surface)] animate-pulse"></div>
                    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6 animate-pulse">
                        <div className="h-6 w-1/2 bg-gray-800 rounded mb-8"></div>
                        <div className="space-y-6">
                            <div className="h-4 w-full bg-gray-800 rounded"></div>
                            <div className="h-4 w-full bg-gray-800 rounded"></div>
                        </div>
                    </div>
                </div>

                <ClipGrid clips={[]} baseUrl={BASE_URL} loading={true} />
            </div>
        );
    }

    if (error || !project) {
        return (
            <div className="container mx-auto px-4 py-12 flex flex-col items-center justify-center min-h-[50vh]">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--error)]/10 text-[var(--error)] mb-4">
                    <AlertCircle className="h-8 w-8" />
                </div>
                <h2 className="text-2xl font-bold text-[var(--foreground)] mb-2">Project not found</h2>
                <p className="text-gray-400 mb-6">{error || "The project you are looking for does not exist."}</p>
                <button
                    onClick={() => router.push('/')}
                    className="inline-flex h-10 items-center justify-center rounded-sm bg-[var(--surface)] border border-[var(--border)] px-4 py-2 text-sm font-medium hover:bg-gray-800 transition-colors"
                >
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back to Dashboard
                </button>
            </div>
        );
    }

    return (
        <div className="container mx-auto px-4 py-8 md:px-6 md:py-12 max-w-6xl animate-in fade-in duration-500">
            <button
                onClick={() => router.push('/')}
                className="inline-flex items-center text-sm text-gray-400 hover:text-[var(--foreground)] transition-colors mb-8"
            >
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Dashboard
            </button>

            <div className="mb-8">
                <h1 className="text-3xl font-bold tracking-tight text-[var(--foreground)] mb-2">
                    {project.title || "Untitled Project"}
                </h1>
                <div className="flex items-center gap-3 text-sm text-gray-400">
                    <span className="font-mono">{project.id}</span>
                    <span>•</span>
                    <span>{new Date(project.created_at).toLocaleDateString()}</span>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-12">
                <div className="lg:col-span-2">
                    <VideoEmbed url={project.youtube_url} />
                </div>

                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6 flex flex-col">
                    <h3 className="text-lg font-semibold mb-6 flex items-center justify-between">
                        Project Status
                        <span className={`text-xs px-2.5 py-1 rounded-sm font-medium ${project.status === 'done' ? 'bg-[var(--success)]/10 text-[var(--success)]' :
                            project.status === 'processing' ? 'bg-yellow-500/10 text-yellow-500 animate-pulse' :
                                'bg-blue-500/10 text-blue-500'
                            }`}>
                            {project.status.charAt(0).toUpperCase() + project.status.slice(1)}
                        </span>
                    </h3>

                    <div className="space-y-4 flex-1">
                        <div className="flex justify-between items-center py-2 border-b border-[var(--border)]">
                            <span className="text-gray-400">Source</span>
                            <a href={project.youtube_url} target="_blank" rel="noreferrer" className="text-[var(--accent)] hover:underline truncate max-w-[150px]" title={project.youtube_url}>
                                YouTube Link
                            </a>
                        </div>
                        <div className="flex justify-between items-center py-2 border-b border-[var(--border)]">
                            <span className="text-gray-400">Total Clips</span>
                            <span className="font-mono">{project.clips?.length || 0}</span>
                        </div>
                        {/* Status-specific messaging */}
                        {(project.status !== 'done' && project.status !== 'error') && (
                            <div className="mt-8 space-y-4">
                                <div className="p-4 bg-[var(--surface)] border border-[var(--border)] rounded-md">
                                    <h4 className="text-sm font-semibold mb-2">Live Progress</h4>
                                    <ProgressBar
                                        stage={wsProgress?.stage || project.status}
                                        percent={wsProgress?.percent || 0}
                                    />
                                </div>

                                <div className="p-4 bg-black border border-[var(--border)] rounded-md font-mono text-xs text-gray-400 h-40 overflow-y-auto flex flex-col-reverse">
                                    <div className="space-y-1">
                                        {logs.map((log, i) => (
                                            <div key={i} className="whitespace-pre-wrap">
                                                <span className="text-gray-500">[{log.time}]</span> {log.text}
                                            </div>
                                        ))}
                                        {logs.length === 0 && (
                                            <div className="text-gray-600 italic">Connecting to server for logs...</div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {project.clips && project.clips.length > 0 ? (
                <div className="pt-8 border-t border-[var(--border)]">
                    <ClipGrid clips={project.clips} baseUrl={BASE_URL} />
                </div>
            ) : (
                project.status === 'done' && (
                    <div className="text-center py-12 text-gray-400 border border-dashed border-[var(--border)] rounded-lg">
                        No clips were generated for this video.
                    </div>
                )
            )}
        </div>
    );
}
