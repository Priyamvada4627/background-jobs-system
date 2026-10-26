import React from 'react';
import { Layers } from 'lucide-react';

interface QueueDepthBarProps {
  queueDepths?: {
    HIGH: number;
    DEFAULT: number;
    LOW: number;
    TOTAL: number;
  };
}

export const QueueDepthBar: React.FC<QueueDepthBarProps> = ({ queueDepths }) => {
  const depths = queueDepths || { HIGH: 0, DEFAULT: 0, LOW: 0, TOTAL: 0 };

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center space-x-2 text-xs text-slate-300">
        <Layers className="w-4 h-4 text-indigo-400" />
        <span className="font-semibold text-slate-200">
          Redis Priority Lanes (6:3:1 Weighted Fair Allocation):
        </span>
      </div>

      <div className="flex items-center space-x-6 text-xs">
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-rose-500"></span>
          <span className="text-rose-400 font-semibold">HIGH:</span>
          <span className="font-mono text-slate-200 font-bold">{depths.HIGH}</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-amber-500"></span>
          <span className="text-amber-400 font-semibold">DEFAULT:</span>
          <span className="font-mono text-slate-200 font-bold">{depths.DEFAULT}</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-slate-400"></span>
          <span className="text-slate-400 font-semibold">LOW:</span>
          <span className="font-mono text-slate-200 font-bold">{depths.LOW}</span>
        </div>
        <div className="pl-4 border-l border-slate-750 flex items-center space-x-1.5">
          <span className="text-indigo-400 font-semibold">TOTAL:</span>
          <span className="font-mono text-indigo-300 font-bold text-sm">{depths.TOTAL}</span>
        </div>
      </div>
    </div>
  );
};
