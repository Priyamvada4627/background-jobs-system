import { useEffect, useRef, useState, useCallback } from 'react';
import { WSEvent } from '../types';

export function useWebSocket(onEvent?: (event: WSEvent) => void) {
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<WSEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    let url: string;
    if (import.meta.env.VITE_WS_URL) {
      url = import.meta.env.VITE_WS_URL;
    } else if (import.meta.env.VITE_API_URL) {
      const apiUrl = import.meta.env.VITE_API_URL;
      const wsProtocol = apiUrl.startsWith('https://') ? 'wss://' : 'ws://';
      const cleanHost = apiUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '');
      url = `${wsProtocol}${cleanHost}/ws`;
    } else if (typeof window !== 'undefined' && window.location.hostname !== 'localhost') {
      url = 'wss://background-jobs-system.onrender.com/ws';
    } else {
      const loc = window.location;
      const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = loc.port === '3000' ? 'localhost:8000' : loc.host;
      url = `${protocol}//${host}/ws`;
    }

    const ws = new WebSocket(url);
    socketRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (messageEvent) => {
      try {
        const payload: WSEvent = JSON.parse(messageEvent.data);
        payload.timestamp = new Date().toISOString();
        setEvents((prev) => [payload, ...prev.slice(0, 99)]);
        if (onEvent) onEvent(payload);
      } catch (err) {
        // Heartbeat or raw text
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      reconnectTimeoutRef.current = window.setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [onEvent]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (socketRef.current) socketRef.current.close();
    };
  }, [connect]);

  return { isConnected, events };
}
