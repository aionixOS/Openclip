"use client";

import { Clip } from "@/lib/types";
import { PlayCircle, Download, User } from "lucide-react";

interface ClipCardProps {
    clip: Clip;
    baseUrl: string;
}

export function ClipCard({ clip, baseUrl }: ClipCardProps) {
    const formatDuration = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div className="group relative flex flex-col overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)] transition-all hover:border-[var(--accent)]/50 hover:shadow-lg hover:-translate-y-1">
            {/* Thumbnail Placeholder */}
            <div className="relative aspect-video w-full bg-gray-900 border-b border-[var(--border)] overflow-hidden">
                <div className="absolute inset-0 flex items-center justify-center">
                    <PlayCircle className="h-12 w-12 text-[var(--accent)] opacity-80 group-hover:scale-110 transition-transform duration-300" />
                </div>
                <div className="absolute bottom-2 right-2 flex items-center gap-2">
                    {clip.face_count !== undefined && clip.face_count > 0 && (
                        <div className="bg-black/80 px-2 py-1 flex items-center gap-1 rounded text-xs text-gray-300 font-medium backdrop-blur-sm">
                            <User className="h-3 w-3" />
                            {clip.face_count}
                        </div>
                    )}
                    <div className="bg-black/80 px-2 py-1 rounded text-xs font-mono font-medium backdrop-blur-sm">
                        {formatDuration(clip.duration)}
                    </div>
                </div>

                {/* Fake Badges */}
                <div className="absolute top-2 left-2 flex gap-2">
                    {clip.reframed && (
                        <span className="bg-[var(--accent)] text-black text-[10px] font-bold px-1.5 py-0.5 rounded shadow-sm">
                            9:16
                        </span>
                    )}
                    {clip.captioned && (
                        <span className="bg-blue-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded shadow-sm">
                            CC
                        </span>
                    )}
                </div>
            </div>

            {/* Video Meta */}
            <div className="p-4 flex flex-col justify-between flex-1">
                <div>
                    <h3 className="font-semibold text-[var(--foreground)] line-clamp-1 mb-1" title={clip.title || ""}>
                        {clip.title || `Clip from ${formatDuration(clip.start_time)} to ${formatDuration(clip.end_time)}`}
                    </h3>

                    {clip.viral_score !== undefined && (
                        <div className={`text-xs font-bold mb-2 flex items-center ${clip.viral_score >= 8 ? "text-green-500" :
                                clip.viral_score >= 5 ? "text-yellow-500" :
                                    "text-gray-500"
                            }`}>
                            {clip.viral_score >= 8 ? "🔥 " : clip.viral_score >= 5 ? "⚡ " : ""}
                            Viral score: {clip.viral_score}/10
                        </div>
                    )}

                    {clip.reason && (
                        <p className="text-xs text-gray-500 italic line-clamp-2 mb-2" title={clip.reason}>
                            {clip.reason}
                        </p>
                    )}

                    {clip.hashtags && clip.hashtags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-2">
                            {clip.hashtags.map((tag, i) => (
                                <span key={i} className="text-[11px] font-medium text-blue-400 bg-blue-400/10 px-1.5 py-0.5 rounded">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    )}

                    {clip.tags && clip.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-2">
                            {clip.tags.map((tag, i) => (
                                <span key={i} className="text-[11px] text-gray-400 bg-gray-700/50 px-1.5 py-0.5 rounded">
                                    {tag}
                                </span>
                            ))}
                        </div>
                    )}
                </div>

                <div className="mt-4 pt-4 border-t border-[var(--border)] flex gap-2">
                    <a
                        href={`${baseUrl}${clip.file_path}`}
                        target="_blank"
                        rel="noreferrer"
                        className="flex-1 inline-flex items-center justify-center gap-2 rounded-sm bg-[var(--accent)]/10 text-[var(--accent)] hover:bg-[var(--accent)]/20 px-3 py-2 text-sm font-medium transition-colors"
                        title="Play Clip"
                    >
                        <PlayCircle className="h-4 w-4" />
                        Preview
                    </a>
                    <a
                        href={`${baseUrl}${clip.file_path}`}
                        download
                        className="flex-1 inline-flex items-center justify-center gap-2 rounded-sm bg-[var(--surface)] border border-[var(--border)] hover:bg-gray-800 text-[var(--foreground)] px-3 py-2 text-sm font-medium transition-colors"
                        title="Download Clip"
                    >
                        <Download className="h-4 w-4" />
                        Save
                    </a>
                </div>
            </div>
        </div>
    );
}
