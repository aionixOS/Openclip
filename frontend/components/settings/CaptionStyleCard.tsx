"use client";

import { CaptionStyle } from "@/lib/types";

export interface CaptionStyleCardProps {
    styleKey: string;
    name: string;
    animation: 'word_by_word' | 'highlight';
    previewColors: {
        text: string;
        highlight: string | null;
        background: string | null;
    };
    selected: boolean;
    onSelect: (key: string) => void;
}

export function CaptionStyleCard({
    styleKey,
    name,
    animation,
    previewColors,
    selected,
    onSelect
}: CaptionStyleCardProps) {
    return (
        <button
            type="button"
            onClick={() => onSelect(styleKey)}
            className={`relative w-full text-left rounded-lg transition-all overflow-hidden border-2 ${
                selected 
                    ? 'border-[#3ecf8e] bg-[#111111]' 
                    : 'border-[var(--border)] bg-[#111111] hover:border-gray-600'
            }`}
        >
            <div className="p-4 flex flex-col gap-4">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <span className="font-semibold text-[var(--foreground)]">{name}</span>
                    {styleKey === "none" && (
                        <span className="text-gray-500 line-through text-lg leading-none" title="No captions">T</span>
                    )}
                </div>

                {/* Preview Area */}
                <div 
                    className="h-16 flex items-center justify-center rounded bg-black/50 overflow-hidden"
                    style={{ backgroundColor: previewColors.background || undefined }}
                >
                    {styleKey === "none" ? (
                        <span className="text-gray-600 font-mono text-sm">(No captions)</span>
                    ) : (
                        <h3 className="text-xl font-bold uppercase tracking-wide">
                            {animation === "highlight" ? (
                                <>
                                    <span style={{ color: previewColors.text, opacity: 0.5 }} className="mr-2">THE</span>
                                    <span style={{ color: previewColors.highlight || previewColors.text }}>QUICK</span>
                                </>
                            ) : (
                                <span style={{ color: previewColors.text }}>THE QUICK</span>
                            )}
                        </h3>
                    )}
                </div>

                {/* Badge */}
                <div className="mt-auto">
                    <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-gray-800 text-gray-300">
                        {animation === 'word_by_word' ? "◾ Word Pop" : "▶ Highlight"}
                    </span>
                </div>
            </div>
        </button>
    );
}
