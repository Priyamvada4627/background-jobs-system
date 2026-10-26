import React from 'react';
import { SystemStats } from '../types';
import { Users, Clock, PlayCircle, CheckCircle2, RotateCcw, AlertOctagon } from 'lucide-react';

interface StatsCardsProps {
  stats: SystemStats | null;
}

export const StatsCards: React.FC<StatsCardsProps> = ({ stats }) => {
  const cards = [
    {
      title: 'Active Workers',
      value: stats?.active_workers_count ?? 0,
      icon: Users,
      color: 'text-emerald-400',
      bgColor: 'bg-emerald-500/10',
      borderColor: 'border-emerald-500/20',
    },
    {
      title: 'Queued',
      value: stats?.jobs_by_status?.QUEUED ?? 0,
      icon: Clock,
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/10',
      borderColor: 'border-blue-500/20',
    },
    {
      title: 'Running',
      value: stats?.jobs_by_status?.RUNNING ?? 0,
      icon: PlayCircle,
      color: 'text-amber-400',
      bgColor: 'bg-amber-500/10',
      borderColor: 'border-amber-500/20',
    },
    {
      title: 'Succeeded',
      value: stats?.jobs_by_status?.SUCCEEDED ?? 0,
      icon: CheckCircle2,
      color: 'text-emerald-500',
      bgColor: 'bg-emerald-500/10',
      borderColor: 'border-emerald-500/20',
    },
    {
      title: 'Retry Wait',
      value: stats?.jobs_by_status?.RETRY_WAIT ?? 0,
      icon: RotateCcw,
      color: 'text-purple-400',
      bgColor: 'bg-purple-500/10',
      borderColor: 'border-purple-500/20',
    },
    {
      title: 'Dead (DLQ)',
      value: stats?.jobs_by_status?.DEAD ?? 0,
      icon: AlertOctagon,
      color: 'text-rose-500',
      bgColor: 'bg-rose-500/10',
      borderColor: 'border-rose-500/20',
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {cards.map((c, i) => {
        const Icon = c.icon;
        return (
          <div
            key={i}
            className={`bg-slate-900 border ${c.borderColor} rounded-xl p-4 flex flex-col justify-between transition hover:border-slate-700`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                {c.title}
              </span>
              <div className={`p-1.5 rounded-lg ${c.bgColor}`}>
                <Icon className={`w-4 h-4 ${c.color}`} />
              </div>
            </div>
            <div className="mt-3">
              <span className={`text-2xl font-bold ${c.color}`}>
                {c.value}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};
