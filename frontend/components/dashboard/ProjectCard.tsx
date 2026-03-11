"use client";

import Link from "next/link";
import { Project } from "@/lib/types";
import { Trash2, Scissors, Clock, AlertCircle, CheckCircle2, Loader2, DownloadCloud } from "lucide-react";
import { cn } from "@/lib/utils";

interface ProjectCardProps {
    project: Project;
    onDelete: (id: string) => void;
}

const statusConfig: Record<Project['status'], { label: string; icon: React.ElementType; className: string }> = {
    pending: { label: "Pending", icon: Clock, className: "bg-gray-500/10 text-gray-400 border-gray-500/20" },
    downloading: { label: "Downloading", icon: DownloadCloud, className: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
    processing: { label: "Processing", icon: Loader2, className: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20" },
    done: { label: "Done", icon: CheckCircle2, className: "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/20" },
    error: { label: "Error", icon: AlertCircle, className: "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/20" },
};

export function ProjectCard({ project, onDelete }: ProjectCardProps) {
    const config = statusConfig[project.status];
    const Icon = config.icon;

    const formattedDate = new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    }).format(new Date(project.created_at));

    return (
        <div className="group relative flex flex-col justify-between rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5 transition-all hover:border-gray-600 hover:shadow-md">
            <div className="flex items-start justify-between">
                <Link href={`/project/${project.id}`} className="block flex-1 pr-4">
                    <h3 className="line-clamp-2 text-lg font-semibold tracking-tight text-[var(--foreground)] group-hover:text-[var(--accent)] transition-colors">
                        {project.title || "Untitled Project"}
                    </h3>
                    <p className="mt-1 text-sm text-gray-400 truncate w-full" title={project.youtube_url}>
                        {project.youtube_url}
                    </p>
                </Link>
                <button
                    onClick={(e) => {
                        e.preventDefault();
                        onDelete(project.id);
                    }}
                    className="text-gray-500 hover:text-[var(--error)] transition-colors p-2 -mr-2 -mt-2 rounded-sm"
                    title="Delete Project"
                >
                    <Trash2 className="h-5 w-5" />
                </button>
            </div>

            <Link href={`/project/${project.id}`} className="block mt-6">
                <div className="flex items-center justify-between text-sm">
                    <div className={cn("inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 text-xs font-semibold", config.className)}>
                        <Icon className={cn("h-3.5 w-3.5", project.status === 'processing' || project.status === 'downloading' ? 'animate-spin' : '')} />
                        {config.label}
                    </div>

                    <div className="flex items-center gap-4 text-gray-400">
                        <div className="flex items-center gap-1.5">
                            <Scissors className="h-4 w-4" />
                            <span>{project.clip_count || 0} clips</span>
                        </div>
                        <span className="text-xs">{formattedDate}</span>
                    </div>
                </div>
            </Link>
        </div>
    );
}
