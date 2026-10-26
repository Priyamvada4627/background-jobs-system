import React from 'react';
import { Job, JobStatus, JobPriority } from '../types';
import { Eye, RotateCw, XCircle, RefreshCw } from 'lucide-react';

interface JobTableProps {
  jobs: Job[];
  loading: boolean;
  selectedStatus: string;
  onSelectStatus: (status: string) => void;
  onRefresh: () => void;
  onViewDetails: (job: Job) => void;
  onRetry: (id: string) => void;
  onCancel: (id: string) => void;
}

export const JobTable: React.FC<JobTableProps> = ({
  jobs,
  loading,
  selectedStatus,
  onSelectStatus,
  onRefresh,
  onViewDetails,
  onRetry,
  onCancel,
}) => {
  const getStatusBadge = (status: JobStatus) => {
    switch (status) {
      case 'QUEUED':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
      case 'RUNNING':
        return 'bg-amber-500/10 text-amber-300 border-amber-500/30 animate-pulse-slow';
      case 'SUCCEEDED':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      case 'RETRY_WAIT':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
      case 'DEAD':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
      case 'CANCELLED':
        return 'bg-slate-500/10 text-slate-400 border-slate-500/30';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  const getPriorityBadge = (priority: JobPriority) => {
    switch (priority) {
      case 'HIGH':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
      case 'DEFAULT':
        return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30';
      case 'LOW':
        return 'bg-slate-500/10 text-slate-400 border-slate-500/30';
    }
  };

  return (
    <div className="space-y-4">
      {/* Controls & Filter Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400">Filter by status:</span>
          <select
            value={selectedStatus}
            onChange={(e) => onSelectStatus(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All Statuses</option>
            <option value="QUEUED">QUEUED</option>
            <option value="RUNNING">RUNNING</option>
            <option value="SUCCEEDED">SUCCEEDED</option>
            <option value="RETRY_WAIT">RETRY_WAIT</option>
            <option value="DEAD">DEAD</option>
            <option value="CANCELLED">CANCELLED</option>
          </select>
        </div>

        <button
          onClick={onRefresh}
          className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center space-x-1.5 py-1 px-2.5 rounded-lg border border-indigo-500/20 bg-indigo-500/5 hover:bg-indigo-500/10 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Table Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/70 border-b border-slate-800 text-slate-400 uppercase font-semibold">
              <tr>
                <th className="px-4 py-3">Job ID</th>
                <th className="px-4 py-3">Task Type</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Attempts</th>
                <th className="px-4 py-3">Created / Scheduled</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300">
              {loading && jobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    Loading jobs...
                  </td>
                </tr>
              ) : jobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    No jobs matching criteria.
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-4 py-3 font-mono text-slate-400">
                      {job.id.substring(0, 8)}...
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-200">
                      {job.task_type}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getPriorityBadge(job.priority)}`}>
                        {job.priority}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${getStatusBadge(job.status)}`}>
                        {job.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {job.attempt_count} / {job.max_retries}
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {new Date(job.created_at).toLocaleTimeString()}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        onClick={() => onViewDetails(job)}
                        className="text-indigo-400 hover:text-indigo-300 inline-flex items-center space-x-1"
                        title="View Details"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>View</span>
                      </button>
                      {['DEAD', 'CANCELLED'].includes(job.status) && (
                        <button
                          onClick={() => onRetry(job.id)}
                          className="text-emerald-400 hover:text-emerald-300 inline-flex items-center space-x-1"
                          title="Retry Job"
                        >
                          <RotateCw className="w-3.5 h-3.5" />
                          <span>Retry</span>
                        </button>
                      )}
                      {['QUEUED', 'RUNNING', 'RETRY_WAIT'].includes(job.status) && (
                        <button
                          onClick={() => onCancel(job.id)}
                          className="text-rose-400 hover:text-rose-300 inline-flex items-center space-x-1"
                          title="Cancel Job"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          <span>Cancel</span>
                        </button>
                      )}
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
