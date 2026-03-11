/**
 * ProgressBar — Displays real-time processing progress.
 */
interface ProgressBarProps {
    progress: number;   // 0 – 100
    message?: string;
}

export default function ProgressBar({ progress, message }: ProgressBarProps) {
    return (
        <div>
            <div
                style={{
                    width: "100%",
                    backgroundColor: "#e0e0e0",
                    borderRadius: "4px",
                    overflow: "hidden",
                }}
            >
                <div
                    style={{
                        width: `${Math.min(100, Math.max(0, progress))}%`,
                        height: "20px",
                        backgroundColor: "#4caf50",
                        transition: "width 0.3s ease",
                    }}
                />
            </div>
            <p>{message ?? `${progress.toFixed(1)}%`}</p>
        </div>
    );
}
