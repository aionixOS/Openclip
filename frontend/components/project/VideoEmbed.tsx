interface VideoEmbedProps {
    url: string;
}

export function VideoEmbed({ url }: VideoEmbedProps) {
    // Extract video ID from youtube URL
    const getOutputVideoId = (url: string) => {
        const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
        const match = url.match(regExp);
        return (match && match[2].length === 11) ? match[2] : null;
    };

    const videoId = getOutputVideoId(url);

    if (!videoId) {
        return (
            <div className="w-full aspect-video flexitems-center justify-center bg-[var(--surface)] text-center text-gray-500 rounded-lg border border-[var(--border)] p-4">
                Invalid YouTube URL
            </div>
        );
    }

    return (
        <div className="w-full aspect-video rounded-lg overflow-hidden border border-[var(--border)] shadow-lg bg-black">
            <iframe
                width="100%"
                height="100%"
                src={`https://www.youtube.com/embed/${videoId}?autoplay=0&rel=0`}
                title="YouTube video player"
                frameBorder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="w-full h-full"
            ></iframe>
        </div>
    );
}
