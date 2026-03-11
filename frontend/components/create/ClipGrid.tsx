"use client";

import { ClipCard } from "@/components/project/ClipCard";
import { Clip } from "@/lib/types";

interface ClipGridProps {
    clips: Clip[];
    baseUrl: string;
    loading?: boolean;
}

export function ClipGrid({ clips, baseUrl, loading = false }: ClipGridProps) {
    if (loading) {
        return (
            <div className="w-full mt-12 animate-in fade-in slide-in-from-bottom-8 duration-700">
                <h2 className="text-2xl font-bold mb-6 flex items-center gap-2 text-[var(--foreground)]">
                    Generating Clips
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] h-64 animate-pulse">
                            <div className="w-full aspect-video bg-gray-900 border-b border-[var(--border)]"></div>
                            <div className="p-4 flex flex-col justify-between h-full">
                                <div className="h-4 bg-gray-800 rounded w-3/4 mb-2"></div>
                                <div className="h-3 bg-gray-800 rounded w-1/2"></div>
                                <div className="mt-4 pt-4 border-t border-[var(--border)] flex gap-2">
                                    <div className="h-8 bg-gray-800 rounded flex-1"></div>
                                    <div className="h-8 bg-gray-800 rounded flex-1"></div>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        );
    }

    if (!clips || clips.length === 0) {
        return null;
    }

    const formatDuration = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div className="w-full mt-12 animate-in fade-in slide-in-from-bottom-8 duration-700">
            <h2 className="text-2xl font-bold mb-6 flex items-center gap-2 text-[var(--foreground)]">
                Generated Clips
                <span className="text-sm font-normal text-gray-500 bg-[var(--surface)] border border-[var(--border)] px-2 py-0.5 rounded-full">
                    {clips.length}
                </span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {clips.map((clip) => (
                    <ClipCard key={clip.id} clip={clip} baseUrl={baseUrl} />
                ))}
            </div>
        </div>
    );
}
