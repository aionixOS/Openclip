"use client";

interface ProjectCardSkeletonProps {
    count?: number;
}

export function ProjectCardSkeleton({ count = 1 }: ProjectCardSkeletonProps) {
    return (
        <>
            {Array.from({ length: count }).map((_, i) => (
                <div key={i} className="group relative flex flex-col justify-between rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5 animate-pulse">
                    <div className="flex items-start justify-between">
                        <div className="w-full pr-4">
                            <div className="h-6 w-3/4 mb-3 bg-gray-800 rounded"></div>
                            <div className="h-4 w-full bg-gray-800 rounded"></div>
                        </div>
                        <div className="h-8 w-8 bg-gray-800 rounded-sm"></div>
                    </div>

                    <div className="mt-6 flex items-center justify-between">
                        <div className="h-6 w-24 bg-gray-800 rounded-sm"></div>

                        <div className="flex items-center gap-4">
                            <div className="h-4 w-16 bg-gray-800 rounded"></div>
                            <div className="h-4 w-20 bg-gray-800 rounded"></div>
                        </div>
                    </div>
                </div>
            ))}
        </>
    );
}
