"use client";

interface ProgressBarProps {
    stage: string;
    percent: number;
    visible?: boolean;
}

export function ProgressBar({ stage, percent, visible = true }: ProgressBarProps) {
    if (!visible) return null;

    // Ensure percentage is between 0 and 100
    const clampedPercent = Math.min(100, Math.max(0, percent));

    const stageConfig: Record<string, { label: string, color: string }> = {
        "downloading": { label: "Downloading video...", color: "#3b82f6" },
        "transcribing": { label: "Extracting captions...", color: "#8b5cf6" },
        "analyzing": { label: "AI finding best moments...", color: "#eab308" },
        "processing": { label: "Cutting & reframing clips...", color: "#3ecf8e" },
        "done": { label: "All clips ready!", color: "#3ecf8e" },
        "error": { label: "Something went wrong", color: "#ff4444" }
    };

    const currentConfig = stageConfig[stage] || { label: stage || "Processing...", color: "var(--accent)" };

    return (
        <div className="w-full max-w-2xl mx-auto mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-end mb-2">
                <span className="text-sm font-medium text-[var(--foreground)]">
                    {currentConfig.label}
                </span>
                <span className="text-xs font-mono text-gray-400">
                    {Math.round(clampedPercent)}%
                </span>
            </div>
            <div className="h-2 w-full bg-[var(--surface)] rounded-full overflow-hidden border border-[var(--border)]">
                <div
                    className="h-full transition-all duration-300 ease-out"
                    style={{ width: `${clampedPercent}%`, backgroundColor: currentConfig.color }}
                />
            </div>
        </div>
    );
}
