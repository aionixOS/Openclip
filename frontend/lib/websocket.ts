import { useEffect, useState, useRef } from "react";
import { ProgressUpdate } from "./types";

export interface ProgressState extends ProgressUpdate {
    connected: boolean;
    logs: string[];
}

export function useProjectProgress(projectId: string | null): ProgressState {
    const [stage, setStage] = useState<string>("Initializing...");
    const [percent, setPercent] = useState<number>(0);
    const [message, setMessage] = useState<string>("");
    const [connected, setConnected] = useState<boolean>(false);
    const [logs, setLogs] = useState<string[]>([]);

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        if (!projectId) {
            setStage("Initializing...");
            setPercent(0);
            setMessage("");
            setLogs([]);
            setConnected(false);
            return;
        }

        setStage("Initializing...");
        setPercent(0);
        setMessage("");
        setLogs([]);

        let isMounted = true;
        const host = window.location.hostname;
        const isReplit = host !== 'localhost' && host !== '127.0.0.1';
        const wsBase = isReplit
            ? `wss://${host.replace(/^(\d+)-/, '8000-')}`
            : 'ws://localhost:8000';
        const WS_URL = `${wsBase}/ws/progress/${projectId}`;

        const connect = () => {
            if (!isMounted) return;

            try {
                const ws = new WebSocket(WS_URL);
                wsRef.current = ws;

                ws.onopen = () => {
                    if (isMounted) {
                        setConnected(true);
                        console.log(`[WebSocket] Connected to project: ${projectId}`);
                    }
                };

                ws.onmessage = (event) => {
                    if (!isMounted) return;
                    try {
                        const data: ProgressUpdate = JSON.parse(event.data);
                        setStage(data.stage || "Processing...");
                        setPercent(data.percent || 0);

                        if (data.message) {
                            setMessage(data.message);
                            setLogs(prev => {
                                const newLog = `[${new Date().toLocaleTimeString()}] ${data.message}`;
                                // Keep last 50 logs
                                return [...prev, newLog].slice(-50);
                            });
                        }
                    } catch (err) {
                        console.error("[WebSocket] Failed to parse message:", err);
                    }
                };

                ws.onclose = () => {
                    if (isMounted) {
                        setConnected(false);
                        console.log("[WebSocket] Disconnected. Reconnecting in 3s...");
                        // Auto-reconnect
                        reconnectTimeoutRef.current = setTimeout(connect, 3000);
                    }
                };

                ws.onerror = () => {
                    // Suppress empty Event object logs when connection fails
                    // The onclose handler will handle reconnecting
                    ws.close();
                };
            } catch (err) {
                console.error("[WebSocket] Setup Error:", err);
                if (isMounted) {
                    reconnectTimeoutRef.current = setTimeout(connect, 3000);
                }
            }
        };

        connect();

        return () => {
            isMounted = false;
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [projectId]);

    return { stage, percent, message, connected, logs };
}
