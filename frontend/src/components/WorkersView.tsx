import React from 'react';
import { Worker } from '../types';
import { Cpu, Server, Activity } from 'lucide-react';

interface WorkersViewProps {
  workers: Worker[];
}

export const WorkersView: React.FC<WorkersViewProps> = ({ workers }) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center space-x-2 text-xs text-slate-400">
        <Cpu className="w-4 h-4 text-indigo-400" />
        <span>Currently Registered Worker Processes</span>
      </div>

      {workers.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500 text-xs">
          No active worker nodes currently running. Start a worker using <code>python -m app.workers.cli</code>.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workers.map((w) => (
            <div
              key={w.worker_id}
              className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3 shadow"
            >
              <div className="flex justify-between items-start">
                <div className="flex items-center space-x-2">
                  <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                    <Server className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div>
                    <p className="font-bold text-slate-200 text-xs">{w.worker_id}</p>
                    <p className="text-slate-400 text-[11px]">
                      {w.hostname} (PID: {w.pid})
                    </p>
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center space-x-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  <span>ONLINE</span>
                </span>
              </div>

              <div className="text-xs text-slate-400 space-y-1.5 bg-slate-950 p-3 rounded-lg border border-slate-850">
                <div className="flex justify-between">
                  <span className="text-slate-500">Current Job:</span>
                  <span className="font-mono text-slate-300 font-medium">
                    {w.current_job_id ? `${w.current_job_id.substring(0, 8)}...` : 'IDLE'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Last Heartbeat:</span>
                  <span className="text-slate-300">
                    {w.last_heartbeat_at ? new Date(w.last_heartbeat_at).toLocaleTimeString() : 'N/A'}
                  </span>
                </div>
                {w.capabilities && (
                  <div className="pt-2 border-t border-slate-800 flex items-center justify-between">
                    <span className="text-slate-500 flex items-center space-x-1">
                      <Activity className="w-3 h-3 text-slate-400" />
                      <span>Concurrency:</span>
                    </span>
                    <span className="font-mono text-slate-300">
                      {w.capabilities.concurrency || 1}
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
