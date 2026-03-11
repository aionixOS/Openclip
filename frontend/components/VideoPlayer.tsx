/**
 * VideoPlayer — Embeds a YouTube video using an iframe.
 */
interface VideoPlayerProps {
    url: string;
}

/**
 * Extract the YouTube video ID from a variety of URL formats.
 */
function extractVideoId(url: string): string | null {
    try {
        const parsed = new URL(url);
        // youtube.com/watch?v=ID
        if (parsed.searchParams.has("v")) {
            return parsed.searchParams.get("v");
        }
        // youtu.be/ID
        if (parsed.hostname === "youtu.be") {
            return parsed.pathname.slice(1);
        }
    } catch {
        // ignore malformed URLs
    }
    return null;
}

export default function VideoPlayer({ url }: VideoPlayerProps) {
    const videoId = extractVideoId(url);

    if (!videoId) {
        return <p>Unable to embed video.</p>;
    }

    return (
        <iframe
            width="560"
            height="315"
            src={`https://www.youtube.com/embed/${videoId}`}
            title="YouTube video player"
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
        />
    );
}
