import React, { useState } from 'react';
import { X } from 'lucide-react';

interface SubmitJobModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (jobData: {
    task_type: string;
    payload: Record<string, any>;
    priority: string;
    max_retries: number;
    timeout_seconds: number;
  }) => Promise<void>;
}

export const SubmitJobModal: React.FC<SubmitJobModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
}) => {
  const [taskType, setTaskType] = useState('email.send');
  const [priority, setPriority] = useState('DEFAULT');
  const [payloadText, setPayloadText] = useState(
    JSON.stringify({ recipient: 'user@example.com', subject: 'System Report' }, null, 2)
  );
  const [maxRetries, setMaxRetries] = useState(3);
  const [timeoutSeconds, setTimeoutSeconds] = useState(60);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    let parsedPayload = {};
    try {
      parsedPayload = JSON.parse(payloadText);
    } catch (err: any) {
      setError(`Invalid JSON payload: ${err.message}`);
      return;
    }

    try {
      setSubmitting(true);
      await onSubmit({
        task_type: taskType,
        payload: parsedPayload,
        priority,
        max_retries: maxRetries,
        timeout_seconds: timeoutSeconds,
      });
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to submit job');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
        <div className="flex justify-between items-center pb-2 border-b border-slate-800">
          <h3 className="text-base font-semibold text-white">Submit New Background Job</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3 text-xs">
          <div>
            <label className="block text-slate-300 mb-1 font-medium">Task Type</label>
            <select
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="email.send">email.send (Sample Email Delivery)</option>
              <option value="report.generate">report.generate (PDF Report Generation)</option>
              <option value="data.export">data.export (Data Export with Rate Limiting)</option>
              <option value="thumbnail.generate">thumbnail.generate (Image Processing)</option>
              <option value="test.flaky_task">test.flaky_task (Flaky Failure Test)</option>
              <option value="test.slow_task">test.slow_task (Long Running Simulation)</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-300 mb-1 font-medium">Priority</label>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="DEFAULT">DEFAULT (Priority 2 - Normal)</option>
              <option value="HIGH">HIGH (Priority 1 - Expedited)</option>
              <option value="LOW">LOW (Priority 3 - Background)</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-300 mb-1 font-medium">Payload (JSON)</label>
            <textarea
              rows={4}
              value={payloadText}
              onChange={(e) => setPayloadText(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-300 mb-1 font-medium">Max Retries</label>
              <input
                type="number"
                min="0"
                max="10"
                value={maxRetries}
                onChange={(e) => setMaxRetries(parseInt(e.target.value, 10))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-slate-300 mb-1 font-medium">Timeout (seconds)</label>
              <input
                type="number"
                min="5"
                max="3600"
                value={timeoutSeconds}
                onChange={(e) => setTimeoutSeconds(parseInt(e.target.value, 10))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          <div className="flex justify-end space-x-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-lg text-xs shadow transition disabled:opacity-50"
            >
              {submitting ? 'Submitting...' : 'Submit Job'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
