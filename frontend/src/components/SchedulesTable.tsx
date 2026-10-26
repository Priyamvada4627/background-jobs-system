import React from 'react';
import { Schedule } from '../types';
import { Calendar, Trash2, Power, RefreshCw } from 'lucide-react';

interface SchedulesTableProps {
  schedules: Schedule[];
  loading: boolean;
  onRefresh: () => void;
  onToggle: (id: string, currentEnabled: boolean) => void;
  onDelete: (id: string) => void;
}

export const SchedulesTable: React.FC<SchedulesTableProps> = ({
  schedules,
  loading,
  onRefresh,
  onToggle,
  onDelete,
}) => {
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div className="flex items-center space-x-2 text-xs text-slate-400">
          <Calendar className="w-4 h-4 text-indigo-400" />
          <span>Configured Cron &amp; Periodic Tasks</span>
        </div>
        <button
          onClick={onRefresh}
          className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center space-x-1.5 py-1 px-2.5 rounded-lg border border-indigo-500/20 bg-indigo-500/5 hover:bg-indigo-500/10 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/70 border-b border-slate-800 text-slate-400 uppercase font-semibold">
              <tr>
                <th className="px-4 py-3">Schedule Name</th>
                <th className="px-4 py-3">Cron Expression</th>
                <th className="px-4 py-3">Task Type</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Last Run</th>
                <th className="px-4 py-3">Next Run</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300">
              {loading && schedules.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    Loading schedules...
                  </td>
                </tr>
              ) : schedules.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    No recurring schedules configured.
                  </td>
                </tr>
              ) : (
                schedules.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-4 py-3 font-semibold text-slate-200">{s.name}</td>
                    <td className="px-4 py-3 font-mono text-indigo-400">{s.cron_expression}</td>
                    <td className="px-4 py-3 text-slate-300">{s.task_type}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                          s.enabled
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : 'bg-slate-500/10 text-slate-400 border-slate-500/30'
                        }`}
                      >
                        {s.enabled ? 'ACTIVE' : 'PAUSED'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {s.last_run_at ? new Date(s.last_run_at).toLocaleString() : 'Never'}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {s.next_run_at ? new Date(s.next_run_at).toLocaleString() : 'N/A'}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        onClick={() => onToggle(s.id, s.enabled)}
                        className={`inline-flex items-center space-x-1 ${
                          s.enabled ? 'text-amber-400 hover:text-amber-300' : 'text-emerald-400 hover:text-emerald-300'
                        }`}
                        title={s.enabled ? 'Pause Schedule' : 'Enable Schedule'}
                      >
                        <Power className="w-3.5 h-3.5" />
                        <span>{s.enabled ? 'Pause' : 'Enable'}</span>
                      </button>
                      <button
                        onClick={() => onDelete(s.id)}
                        className="text-rose-400 hover:text-rose-300 inline-flex items-center space-x-1"
                        title="Delete Schedule"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
