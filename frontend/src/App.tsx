import React, { useState, useEffect, useCallback } from 'react';
import { Job, Schedule, SystemStats } from './types';
import {
  fetchStats,
  fetchJobs,
  fetchJobById,
  createJob,
  retryJob,
  cancelJob,
  fetchSchedules,
  updateSchedule,
  deleteSchedule,
} from './api/client';
import { useWebSocket } from './hooks/useWebSocket';
import { StatsCards } from './components/StatsCards';
import { QueueDepthBar } from './components/QueueDepthBar';
import { JobTable } from './components/JobTable';
import { SubmitJobModal } from './components/SubmitJobModal';
import { JobDetailModal } from './components/JobDetailModal';
import { SchedulesTable } from './components/SchedulesTable';
import { WorkersView } from './components/WorkersView';
import { LiveActivityFeed } from './components/LiveActivityFeed';
import { Zap, Plus, Wifi, WifiOff } from 'lucide-react';

export const App: React.FC = () => {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [activeTab, setActiveTab] = useState<'jobs' | 'workers' | 'schedules' | 'events'>('jobs');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [jobsLoading, setJobsLoading] = useState(false);
  const [schedulesLoading, setSchedulesLoading] = useState(false);

  // Modals state
  const [isSubmitModalOpen, setIsSubmitModalOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const data = await fetchStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      setJobsLoading(true);
      const data = await fetchJobs(statusFilter || undefined, undefined, 1, 30);
      setJobs(data.items);
    } catch (err) {
      console.error('Failed to load jobs:', err);
    } finally {
      setJobsLoading(false);
    }
  }, [statusFilter]);

  const loadSchedules = useCallback(async () => {
    try {
      setSchedulesLoading(true);
      const data = await fetchSchedules();
      setSchedules(data);
    } catch (err) {
      console.error('Failed to load schedules:', err);
    } finally {
      setSchedulesLoading(false);
    }
  }, []);

  // WebSocket live event handler
  const handleWSEvent = useCallback(() => {
    loadStats();
    if (activeTab === 'jobs') loadJobs();
  }, [loadStats, loadJobs, activeTab]);

  const { isConnected, events } = useWebSocket(handleWSEvent);

  useEffect(() => {
    loadStats();
    loadJobs();
    loadSchedules();
    const interval = setInterval(loadStats, 5000);
    return () => clearInterval(interval);
  }, [loadStats, loadJobs, loadSchedules]);

  const handleCreateJob = async (jobData: any) => {
    await createJob(jobData);
    await Promise.all([loadStats(), loadJobs()]);
  };

  const handleRetryJob = async (id: string) => {
    try {
      await retryJob(id);
      await Promise.all([loadStats(), loadJobs()]);
    } catch (err: any) {
      alert(`Retry failed: ${err.message}`);
    }
  };

  const handleCancelJob = async (id: string) => {
    try {
      await cancelJob(id);
      await Promise.all([loadStats(), loadJobs()]);
    } catch (err: any) {
      alert(`Cancel failed: ${err.message}`);
    }
  };

  const handleViewJobDetails = async (job: Job) => {
    try {
      const freshJob = await fetchJobById(job.id);
      setSelectedJob(freshJob);
    } catch {
      setSelectedJob(job);
    }
  };

  const handleToggleSchedule = async (id: string, currentEnabled: boolean) => {
    try {
      await updateSchedule(id, { enabled: !currentEnabled });
      await loadSchedules();
    } catch (err: any) {
      alert(`Failed to toggle schedule: ${err.message}`);
    }
  };

  const handleDeleteSchedule = async (id: string) => {
    if (!confirm('Are you sure you want to delete this schedule?')) return;
    try {
      await deleteSchedule(id);
      await loadSchedules();
    } catch (err: any) {
      alert(`Failed to delete schedule: ${err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-semibold leading-none text-white">
                Background Job System
              </h1>
              <p className="text-xs text-slate-400 mt-1">
                Distributed Task Queue &amp; Engine
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            {/* Live Streaming Indicator */}
            <div className="flex items-center space-x-2 text-xs px-3 py-1.5 rounded-full border border-slate-700 bg-slate-850">
              {isConnected ? (
                <>
                  <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-slate-300 font-medium">Live Stream</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-3.5 h-3.5 text-rose-500" />
                  <span className="text-slate-400 font-medium">Reconnecting...</span>
                </>
              )}
            </div>

            <button
              onClick={() => setIsSubmitModalOpen(true)}
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg shadow transition flex items-center space-x-1.5"
            >
              <Plus className="w-4 h-4" />
              <span>Submit Job</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Real-Time Metrics Overview */}
        <StatsCards stats={stats} />

        {/* Priority Queues Bar */}
        <QueueDepthBar queueDepths={stats?.queue_depths} />

        {/* Navigation Tabs */}
        <div>
          <div className="border-b border-slate-800 flex space-x-8 text-sm">
            <button
              onClick={() => {
                setActiveTab('jobs');
                loadJobs();
              }}
              className={`pb-3 border-b-2 font-medium transition ${
                activeTab === 'jobs'
                  ? 'border-indigo-500 text-indigo-400'
                  : 'border-transparent text-slate-400 hover:text-slate-300'
              }`}
            >
              Jobs
            </button>
            <button
              onClick={() => setActiveTab('workers')}
              className={`pb-3 border-b-2 font-medium transition ${
                activeTab === 'workers'
                  ? 'border-indigo-500 text-indigo-400'
                  : 'border-transparent text-slate-400 hover:text-slate-300'
              }`}
            >
              Active Workers ({stats?.active_workers_count ?? 0})
            </button>
            <button
              onClick={() => {
                setActiveTab('schedules');
                loadSchedules();
              }}
              className={`pb-3 border-b-2 font-medium transition ${
                activeTab === 'schedules'
                  ? 'border-indigo-500 text-indigo-400'
                  : 'border-transparent text-slate-400 hover:text-slate-300'
              }`}
            >
              Recurring Schedules ({stats?.enabled_schedules_count ?? 0})
            </button>
            <button
              onClick={() => setActiveTab('events')}
              className={`pb-3 border-b-2 font-medium transition ${
                activeTab === 'events'
                  ? 'border-indigo-500 text-indigo-400'
                  : 'border-transparent text-slate-400 hover:text-slate-300'
              }`}
            >
              Live Event Stream
            </button>
          </div>

          <div className="mt-6">
            {activeTab === 'jobs' && (
              <JobTable
                jobs={jobs}
                loading={jobsLoading}
                selectedStatus={statusFilter}
                onSelectStatus={(st) => {
                  setStatusFilter(st);
                }}
                onRefresh={loadJobs}
                onViewDetails={handleViewJobDetails}
                onRetry={handleRetryJob}
                onCancel={handleCancelJob}
              />
            )}

            {activeTab === 'workers' && (
              <WorkersView workers={stats?.active_workers ?? []} />
            )}

            {activeTab === 'schedules' && (
              <SchedulesTable
                schedules={schedules}
                loading={schedulesLoading}
                onRefresh={loadSchedules}
                onToggle={handleToggleSchedule}
                onDelete={handleDeleteSchedule}
              />
            )}

            {activeTab === 'events' && <LiveActivityFeed events={events} />}
          </div>
        </div>
      </main>

      {/* Modals */}
      <SubmitJobModal
        isOpen={isSubmitModalOpen}
        onClose={() => setIsSubmitModalOpen(false)}
        onSubmit={handleCreateJob}
      />

      <JobDetailModal
        job={selectedJob}
        onClose={() => setSelectedJob(null)}
      />
    </div>
  );
};

export default App;
