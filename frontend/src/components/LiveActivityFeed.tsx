import React from 'react';
import { WSEvent } from '../types';
import { Radio } from 'lucide-react';

interface LiveActivityFeedProps {
  events: WSEvent[];
}

export const LiveActivityFeed: React.FC<LiveActivityFeedProps> = ({ events }) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center space-x-2 text-xs text-slate-400">
        <Radio className="w-4 h-4 text-emerald-400" />
        <span>Real-Time WebSocket State Transitions Stream</span>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-xs max-h-[500px] overflow-y-auto space-y-2">
        {events.length === 0 ? (
          <div className="text-slate-500 text-center py-8">
            Listening for live system state transitions...
          </div>
        ) : (
          events.map((ev, idx) => (
            <div
              key={idx}
              className="flex items-start space-x-2 py-1.5 border-b border-slate-800/60 last:border-b-0"
            >
              <span className="text-slate-500 text-[11px]">
                [{ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : 'now'}]
              </span>
              <span className="text-indigo-400 font-semibold">{ev.event}:</span>
              <span className="text-slate-300 truncate">
                {JSON.stringify(ev.data)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
