import React from 'react';
import { Job } from '../types';
import { X, CheckCircle, XCircle, Clock } from 'lucide-react';

interface JobDetailModalProps {
  job: Job | null;
  onClose: () => void;
}

export const JobDetailModal: React.FC<JobDetailModalProps> = ({ job, onClose }) => {
  if (!job) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center pb-2 border-b border-slate-800">
          <div>
            <h3 className="text-base font-semibold text-white">{job.task_type}</h3>
            <p className="text-xs text-slate-400 font-mono mt-0.5">{job.id}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Overview Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs">
          <div>
            <span className="text-slate-500">Status</span>
            <p className="font-bold text-slate-200 mt-0.5">{job.status}</p>
          </div>
          <div>
            <span className="text-slate-500">Priority</span>
            <p className="font-bold text-slate-200 mt-0.5">{job.priority}</p>
          </div>
          <div>
            <span className="text-slate-500">Attempt Count</span>
            <p className="font-bold text-slate-200 mt-0.5">
              {job.attempt_count} / {job.max_retries}
            </p>
          </div>
          <div>
            <span className="text-slate-500">Timeout</span>
            <p className="font-bold text-slate-200 mt-0.5">{job.timeout_seconds}s</p>
          </div>
          <div>
            <span className="text-slate-500">Created At</span>
            <p className="text-slate-300 mt-0.5">{new Date(job.created_at).toLocaleString()}</p>
          </div>
          <div>
            <span className="text-slate-500">Updated At</span>
            <p className="text-slate-300 mt-0.5">{new Date(job.updated_at).toLocaleString()}</p>
          </div>
        </div>

        {/* Payload */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-slate-400">Payload</label>
          <pre className="bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-emerald-400 text-xs overflow-x-auto">
            {JSON.stringify(job.payload, null, 2)}
          </pre>
        </div>

        {/* Result */}
        {job.result && (
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-400">Result</label>
            <pre className="bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-blue-400 text-xs overflow-x-auto">
              {JSON.stringify(job.result, null, 2)}
            </pre>
          </div>
        )}

        {/* Last Error */}
        {job.last_error && (
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-400">Last Error</label>
            <pre className="bg-slate-950 p-3 rounded-xl border border-rose-500/30 font-mono text-rose-400 text-xs overflow-x-auto whitespace-pre-wrap">
              {job.last_error}
            </pre>
          </div>
        )}

        {/* Attempts History */}
        {job.attempts && job.attempts.length > 0 && (
          <div className="space-y-2">
            <label className="text-xs font-medium text-slate-400">
              Execution Attempts ({job.attempts.length})
            </label>
            <div className="space-y-2">
              {job.attempts.map((att) => (
                <div
                  key={att.id}
                  className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-xs space-y-1"
                >
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-slate-300">
                      Attempt #{att.attempt_number} (Worker: {att.worker_id})
                    </span>
                    <span
                      className={`inline-flex items-center space-x-1 font-bold ${
                        att.outcome === 'SUCCEEDED' ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {att.outcome === 'SUCCEEDED' ? (
                        <CheckCircle className="w-3.5 h-3.5" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5" />
                      )}
                      <span>{att.outcome}</span>
                    </span>
                  </div>
                  <div className="flex items-center space-x-3 text-slate-500 text-[11px]">
                    <span className="flex items-center space-x-1">
                      <Clock className="w-3 h-3" />
                      <span>{att.duration_ms} ms</span>
                    </span>
                    <span>Started: {new Date(att.started_at).toLocaleTimeString()}</span>
                  </div>
                  {att.error_message && (
                    <p className="text-rose-400 text-[11px] mt-1">{att.error_message}</p>
                  )}
                  {att.traceback_text && (
                    <pre className="mt-1 bg-slate-900 p-2 rounded text-[10px] font-mono text-slate-400 overflow-x-auto">
                      {att.traceback_text}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex justify-end pt-3 border-t border-slate-800">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
