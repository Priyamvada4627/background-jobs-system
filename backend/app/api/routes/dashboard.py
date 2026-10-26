import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Dashboard"])

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Background Job Management System — Operational Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 50: '#eef2ff', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca' }
          }
        }
      }
    }
  </script>
  <style>
    @keyframes pulse-slow { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    .animate-pulse-slow { animation: pulse-slow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans antialiased">
  <!-- Top Navigation Bar -->
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30">
          ⚡
        </div>
        <div>
          <h1 class="text-base font-semibold leading-none text-white">Background Job System</h1>
          <p class="text-xs text-slate-400 mt-1">Distributed Task Queue &amp; Engine</p>
        </div>
      </div>

      <div class="flex items-center space-x-4">
        <!-- WebSocket Connection Indicator -->
        <div class="flex items-center space-x-2 text-xs px-3 py-1.5 rounded-full border border-slate-700 bg-slate-850">
          <span id="wsIndicator" class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
          <span id="wsStatusText" class="text-slate-300 font-medium">Connecting...</span>
        </div>

        <button onclick="openSubmitModal()" class="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg shadow transition flex items-center space-x-1.5">
          <span>+</span>
          <span>Submit Job</span>
        </button>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
    
    <!-- Real-Time Metrics Row -->
    <section class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Active Workers</p>
        <p id="metricActiveWorkers" class="text-2xl font-bold text-emerald-400 mt-2">0</p>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Queued Jobs</p>
        <p id="metricQueued" class="text-2xl font-bold text-blue-400 mt-2">0</p>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Running Jobs</p>
        <p id="metricRunning" class="text-2xl font-bold text-amber-400 mt-2">0</p>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Succeeded</p>
        <p id="metricSucceeded" class="text-2xl font-bold text-emerald-500 mt-2">0</p>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Retry Wait</p>
        <p id="metricRetryWait" class="text-2xl font-bold text-purple-400 mt-2">0</p>
      </div>
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <p class="text-xs font-medium text-slate-400 uppercase tracking-wider">Dead (DLQ)</p>
        <p id="metricDead" class="text-2xl font-bold text-rose-500 mt-2">0</p>
      </div>
    </section>

    <!-- Priority Queue Lanes Banner -->
    <div class="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center space-x-2 text-xs text-slate-300">
        <span class="font-semibold text-slate-200">Redis Queue Depths (6:3:1 Weighted Fair Schedule):</span>
      </div>
      <div class="flex items-center space-x-6 text-xs">
        <div><span class="text-rose-400 font-semibold">HIGH:</span> <span id="queueHigh" class="font-mono ml-1 font-bold">0</span></div>
        <div><span class="text-amber-400 font-semibold">DEFAULT:</span> <span id="queueDefault" class="font-mono ml-1 font-bold">0</span></div>
        <div><span class="text-slate-400 font-semibold">LOW:</span> <span id="queueLow" class="font-mono ml-1 font-bold">0</span></div>
        <div class="pl-3 border-l border-slate-700"><span class="text-indigo-400 font-semibold">TOTAL:</span> <span id="queueTotal" class="font-mono ml-1 font-bold">0</span></div>
      </div>
    </div>

    <!-- Tabbed Interface -->
    <div>
      <div class="border-b border-slate-800 flex space-x-8 text-sm">
        <button onclick="switchTab('jobs')" id="tabBtnJobs" class="pb-3 border-b-2 border-indigo-500 text-indigo-400 font-medium">Jobs</button>
        <button onclick="switchTab('workers')" id="tabBtnWorkers" class="pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-300 font-medium">Active Workers</button>
        <button onclick="switchTab('schedules')" id="tabBtnSchedules" class="pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-300 font-medium">Cron Schedules</button>
        <button onclick="switchTab('events')" id="tabBtnEvents" class="pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-300 font-medium">Live Activity Stream</button>
      </div>

      <!-- Tab 1: Jobs View -->
      <div id="tabContentJobs" class="mt-6 space-y-4">
        <!-- Filter Bar -->
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-center space-x-2">
            <span class="text-xs text-slate-400">Status filter:</span>
            <select id="statusFilter" onchange="fetchJobs()" class="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500">
              <option value="">All Statuses</option>
              <option value="QUEUED">QUEUED</option>
              <option value="RUNNING">RUNNING</option>
              <option value="SUCCEEDED">SUCCEEDED</option>
              <option value="RETRY_WAIT">RETRY_WAIT</option>
              <option value="DEAD">DEAD</option>
              <option value="CANCELLED">CANCELLED</option>
            </select>
          </div>
          <button onclick="fetchJobs()" class="text-xs text-indigo-400 hover:text-indigo-300 flex items-center space-x-1">
            <span>↻ Refresh Jobs</span>
          </button>
        </div>

        <!-- Jobs Table -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead class="bg-slate-850 border-b border-slate-800 text-slate-400 uppercase font-semibold">
                <tr>
                  <th class="px-4 py-3">Job ID</th>
                  <th class="px-4 py-3">Task Type</th>
                  <th class="px-4 py-3">Priority</th>
                  <th class="px-4 py-3">Status</th>
                  <th class="px-4 py-3">Attempts</th>
                  <th class="px-4 py-3">Scheduled At</th>
                  <th class="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody id="jobsTableBody" class="divide-y divide-slate-800 text-slate-300">
                <tr>
                  <td colspan="7" class="px-4 py-8 text-center text-slate-500">Loading jobs...</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 2: Workers View -->
      <div id="tabContentWorkers" class="mt-6 hidden space-y-4">
        <div id="workersGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 text-center text-slate-500 col-span-3">
            Loading active workers...
          </div>
        </div>
      </div>

      <!-- Tab 3: Schedules View -->
      <div id="tabContentSchedules" class="mt-6 hidden space-y-4">
        <div class="flex justify-end">
          <button onclick="fetchSchedules()" class="text-xs text-indigo-400 hover:text-indigo-300">↻ Refresh Schedules</button>
        </div>
        <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-850 border-b border-slate-800 text-slate-400 uppercase font-semibold">
              <tr>
                <th class="px-4 py-3">Name</th>
                <th class="px-4 py-3">Cron Expression</th>
                <th class="px-4 py-3">Task Type</th>
                <th class="px-4 py-3">Status</th>
                <th class="px-4 py-3">Last Run</th>
                <th class="px-4 py-3">Next Run</th>
              </tr>
            </thead>
            <tbody id="schedulesTableBody" class="divide-y divide-slate-800 text-slate-300">
              <tr>
                <td colspan="6" class="px-4 py-8 text-center text-slate-500">Loading schedules...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Tab 4: Live Event Log -->
      <div id="tabContentEvents" class="mt-6 hidden space-y-4">
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 font-mono text-xs max-h-96 overflow-y-auto space-y-2" id="eventLogContainer">
          <div class="text-slate-500">Waiting for live WebSocket events...</div>
        </div>
      </div>
    </div>
  </main>

  <!-- Submit Job Modal -->
  <div id="submitModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
      <div class="flex justify-between items-center pb-2 border-b border-slate-800">
        <h3 class="text-base font-semibold text-white">Submit New Background Job</h3>
        <button onclick="closeSubmitModal()" class="text-slate-400 hover:text-white">&times;</button>
      </div>

      <div class="space-y-3 text-xs">
        <div>
          <label class="block text-slate-300 mb-1 font-medium">Task Type</label>
          <select id="modalTaskType" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-200">
            <option value="email.send">email.send (Sample Email Delivery)</option>
            <option value="report.generate">report.generate (PDF Report Generation)</option>
            <option value="data.export">data.export (Data Export with Rate Limiting)</option>
            <option value="thumbnail.generate">thumbnail.generate (Image Processing)</option>
            <option value="test.flaky_task">test.flaky_task (Flaky Failure Test)</option>
            <option value="test.slow_task">test.slow_task (Long Running Simulation)</option>
          </select>
        </div>

        <div>
          <label class="block text-slate-300 mb-1 font-medium">Priority</label>
          <select id="modalPriority" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-200">
            <option value="DEFAULT">DEFAULT (Priority 2)</option>
            <option value="HIGH">HIGH (Priority 1 - Expedited)</option>
            <option value="LOW">LOW (Priority 3 - Background)</option>
          </select>
        </div>

        <div>
          <label class="block text-slate-300 mb-1 font-medium">Payload (JSON)</label>
          <textarea id="modalPayload" rows="4" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 font-mono text-slate-200">{"recipient": "operator@example.com", "subject": "System Verification"}</textarea>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-slate-300 mb-1 font-medium">Max Retries</label>
            <input id="modalMaxRetries" type="number" value="3" min="0" max="10" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-200" />
          </div>
          <div>
            <label class="block text-slate-300 mb-1 font-medium">Timeout (seconds)</label>
            <input id="modalTimeout" type="number" value="60" min="5" max="3600" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-slate-200" />
          </div>
        </div>
      </div>

      <div class="flex justify-end space-x-3 pt-3 border-t border-slate-800">
        <button onclick="closeSubmitModal()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs">Cancel</button>
        <button onclick="submitJob()" id="modalSubmitBtn" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-lg text-xs shadow">Submit Job</button>
      </div>
    </div>
  </div>

  <!-- Job Detail Modal -->
  <div id="detailModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
      <div class="flex justify-between items-center pb-2 border-b border-slate-800">
        <h3 id="detailModalTitle" class="text-base font-semibold text-white">Job Details</h3>
        <button onclick="closeDetailModal()" class="text-slate-400 hover:text-white">&times;</button>
      </div>
      <div id="detailModalContent" class="space-y-4 text-xs">
        <!-- Rendered dynamically -->
      </div>
    </div>
  </div>

  <!-- Dashboard JavaScript Logic -->
  <script>
    let activeTab = 'jobs';
    let socket = null;

    function switchTab(tab) {
      activeTab = tab;
      ['jobs', 'workers', 'schedules', 'events'].forEach(t => {
        const btn = document.getElementById('tabBtn' + t.charAt(0).toUpperCase() + t.slice(1));
        const content = document.getElementById('tabContent' + t.charAt(0).toUpperCase() + t.slice(1));
        if (t === tab) {
          btn.className = "pb-3 border-b-2 border-indigo-500 text-indigo-400 font-medium";
          content.classList.remove('hidden');
        } else {
          btn.className = "pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-300 font-medium";
          content.classList.add('hidden');
        }
      });
      if (tab === 'jobs') fetchJobs();
      if (tab === 'workers') fetchStats();
      if (tab === 'schedules') fetchSchedules();
    }

    function initWebSocket() {
      const loc = window.location;
      const wsProtocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${loc.host}/ws`;

      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        document.getElementById('wsIndicator').className = 'w-2.5 h-2.5 rounded-full bg-emerald-500';
        document.getElementById('wsStatusText').innerText = 'Live Streaming';
        logEvent('WebSocket connected', 'Connected to real-time engine stream');
      };

      socket.onclose = () => {
        document.getElementById('wsIndicator').className = 'w-2.5 h-2.5 rounded-full bg-rose-500';
        document.getElementById('wsStatusText').innerText = 'Disconnected';
        setTimeout(initWebSocket, 3000);
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          logEvent(msg.event, JSON.stringify(msg.data));
          // Live refresh stats and jobs when state changes occur
          fetchStats();
          if (activeTab === 'jobs') fetchJobs();
        } catch (e) {
          // Heartbeat pong etc.
        }
      };
    }

    function logEvent(title, detail) {
      const container = document.getElementById('eventLogContainer');
      const time = new Date().toLocaleTimeString();
      const div = document.createElement('div');
      div.className = "flex items-start space-x-2 py-1 border-b border-slate-800/50";
      div.innerHTML = `<span class="text-slate-500">[${time}]</span> <span class="text-indigo-400 font-semibold">${title}:</span> <span class="text-slate-300 truncate">${detail}</span>`;
      container.insertBefore(div, container.firstChild);
    }

    async function fetchStats() {
      try {
        const res = await fetch('/stats');
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById('metricActiveWorkers').innerText = data.active_workers_count || 0;
        document.getElementById('metricQueued').innerText = data.jobs_by_status?.QUEUED || 0;
        document.getElementById('metricRunning').innerText = data.jobs_by_status?.RUNNING || 0;
        document.getElementById('metricSucceeded').innerText = data.jobs_by_status?.SUCCEEDED || 0;
        document.getElementById('metricRetryWait').innerText = data.jobs_by_status?.RETRY_WAIT || 0;
        document.getElementById('metricDead').innerText = data.jobs_by_status?.DEAD || 0;

        document.getElementById('queueHigh').innerText = data.queue_depths?.HIGH || 0;
        document.getElementById('queueDefault').innerText = data.queue_depths?.DEFAULT || 0;
        document.getElementById('queueLow').innerText = data.queue_depths?.LOW || 0;
        document.getElementById('queueTotal').innerText = data.queue_depths?.TOTAL || 0;

        renderWorkers(data.active_workers || []);
      } catch (err) {
        console.error('Failed to fetch stats:', err);
      }
    }

    function renderWorkers(workers) {
      const container = document.getElementById('workersGrid');
      if (!workers.length) {
        container.innerHTML = '<div class="bg-slate-900 border border-slate-800 rounded-xl p-5 text-center text-slate-500 col-span-3">No active workers currently registered.</div>';
        return;
      }
      container.innerHTML = workers.map(w => `
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div class="flex justify-between items-start">
            <div>
              <p class="font-bold text-slate-200">${w.worker_id}</p>
              <p class="text-slate-400 text-xs">${w.hostname} (PID: ${w.pid})</p>
            </div>
            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">ALIVE</span>
          </div>
          <div class="text-xs text-slate-400 space-y-1">
            <p><span class="text-slate-500">Current Job:</span> <span class="font-mono text-slate-300">${w.current_job_id || 'IDLE'}</span></p>
            <p><span class="text-slate-500">Last Heartbeat:</span> <span class="text-slate-300">${w.last_heartbeat_at ? new Date(w.last_heartbeat_at).toLocaleTimeString() : 'N/A'}</span></p>
          </div>
        </div>
      `).join('');
    }

    async function fetchJobs() {
      try {
        const filter = document.getElementById('statusFilter').value;
        const url = filter ? `/jobs?status=${filter}&page_size=30` : '/jobs?page_size=30';
        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        const tbody = document.getElementById('jobsTableBody');

        if (!data.items || data.items.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-slate-500">No jobs found.</td></tr>';
          return;
        }

        tbody.innerHTML = data.items.map(job => {
          let statusColor = "bg-slate-800 text-slate-300 border-slate-700";
          let pulse = "";
          if (job.status === "QUEUED") statusColor = "bg-blue-500/20 text-blue-400 border-blue-500/30";
          else if (job.status === "RUNNING") {
            statusColor = "bg-amber-500/20 text-amber-300 border-amber-500/30";
            pulse = "animate-pulse-slow";
          }
          else if (job.status === "SUCCEEDED") statusColor = "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
          else if (job.status === "RETRY_WAIT") statusColor = "bg-purple-500/20 text-purple-400 border-purple-500/30";
          else if (job.status === "DEAD") statusColor = "bg-rose-500/20 text-rose-400 border-rose-500/30";
          else if (job.status === "CANCELLED") statusColor = "bg-slate-500/20 text-slate-400 border-slate-500/30";

          return `
            <tr class="hover:bg-slate-850 transition">
              <td class="px-4 py-3 font-mono text-slate-400">${job.id.substring(0, 8)}...</td>
              <td class="px-4 py-3 font-medium text-slate-200">${job.task_type}</td>
              <td class="px-4 py-3">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold ${job.priority === 'HIGH' ? 'bg-rose-500/20 text-rose-400' : (job.priority === 'LOW' ? 'bg-slate-500/20 text-slate-400' : 'bg-indigo-500/20 text-indigo-400')}">${job.priority}</span>
              </td>
              <td class="px-4 py-3">
                <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${statusColor} ${pulse}">${job.status}</span>
              </td>
              <td class="px-4 py-3 font-mono">${job.attempt_count} / ${job.max_retries}</td>
              <td class="px-4 py-3 text-slate-400">${new Date(job.created_at).toLocaleTimeString()}</td>
              <td class="px-4 py-3 text-right space-x-2">
                <button onclick="viewJobDetails('${job.id}')" class="text-indigo-400 hover:text-indigo-300">View</button>
                ${['DEAD', 'CANCELLED'].includes(job.status) ? `<button onclick="retryJob('${job.id}')" class="text-emerald-400 hover:text-emerald-300">Retry</button>` : ''}
                ${['QUEUED', 'RUNNING', 'RETRY_WAIT'].includes(job.status) ? `<button onclick="cancelJob('${job.id}')" class="text-rose-400 hover:text-rose-300">Cancel</button>` : ''}
              </td>
            </tr>
          `;
        }).join('');
      } catch (err) {
        console.error('Failed to fetch jobs:', err);
      }
    }

    async function viewJobDetails(jobId) {
      try {
        const res = await fetch(`/jobs/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();
        
        document.getElementById('detailModalTitle').innerText = `Job: ${job.task_type} (${job.id})`;
        document.getElementById('detailModalContent').innerHTML = `
          <div class="grid grid-cols-2 gap-4 bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div><span class="text-slate-500">Status:</span> <span class="font-bold text-slate-200">${job.status}</span></div>
            <div><span class="text-slate-500">Priority:</span> <span class="font-bold text-slate-200">${job.priority}</span></div>
            <div><span class="text-slate-500">Attempt Count:</span> <span class="font-bold text-slate-200">${job.attempt_count} / ${job.max_retries}</span></div>
            <div><span class="text-slate-500">Timeout:</span> <span class="font-bold text-slate-200">${job.timeout_seconds}s</span></div>
            <div><span class="text-slate-500">Created:</span> <span class="text-slate-300">${new Date(job.created_at).toLocaleString()}</span></div>
            <div><span class="text-slate-500">Updated:</span> <span class="text-slate-300">${new Date(job.updated_at).toLocaleString()}</span></div>
          </div>
          <div>
            <p class="font-medium text-slate-300 mb-1">Payload:</p>
            <pre class="bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-emerald-400 overflow-x-auto">${JSON.stringify(job.payload, null, 2)}</pre>
          </div>
          ${job.result ? `
          <div>
            <p class="font-medium text-slate-300 mb-1">Result:</p>
            <pre class="bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-blue-400 overflow-x-auto">${JSON.stringify(job.result, null, 2)}</pre>
          </div>` : ''}
          ${job.last_error ? `
          <div>
            <p class="font-medium text-slate-300 mb-1">Last Error:</p>
            <pre class="bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-rose-400 overflow-x-auto">${job.last_error}</pre>
          </div>` : ''}
          ${job.attempts && job.attempts.length > 0 ? `
          <div>
            <p class="font-medium text-slate-300 mb-1">Execution Attempts (${job.attempts.length}):</p>
            <div class="space-y-2">
              ${job.attempts.map(a => `
                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 text-[11px] space-y-1">
                  <div class="flex justify-between">
                    <span class="font-semibold text-slate-200">Attempt #${a.attempt_number} (Worker: ${a.worker_id})</span>
                    <span class="font-bold ${a.outcome === 'SUCCEEDED' ? 'text-emerald-400' : 'text-rose-400'}">${a.outcome}</span>
                  </div>
                  <p class="text-slate-400">Duration: ${a.duration_ms}ms | Started: ${new Date(a.started_at).toLocaleTimeString()}</p>
                  ${a.error_message ? `<p class="text-rose-400">${a.error_message}</p>` : ''}
                </div>
              `).join('')}
            </div>
          </div>` : ''}
        `;
        document.getElementById('detailModal').classList.remove('hidden');
      } catch (err) {
        alert('Failed to load job details');
      }
    }

    function closeDetailModal() {
      document.getElementById('detailModal').classList.add('hidden');
    }

    async function retryJob(jobId) {
      if (!confirm(`Are you sure you want to retry job ${jobId}?`)) return;
      try {
        const res = await fetch(`/jobs/${jobId}/retry`, { method: 'POST' });
        if (res.ok) {
          fetchJobs();
          fetchStats();
        } else {
          const err = await res.json();
          alert('Failed to retry: ' + (err.detail || 'Unknown error'));
        }
      } catch (e) {
        alert('Network error while retrying');
      }
    }

    async function cancelJob(jobId) {
      if (!confirm(`Are you sure you want to cancel job ${jobId}?`)) return;
      try {
        const res = await fetch(`/jobs/${jobId}/cancel`, { method: 'POST' });
        if (res.ok) {
          fetchJobs();
          fetchStats();
        } else {
          const err = await res.json();
          alert('Failed to cancel: ' + (err.detail || 'Unknown error'));
        }
      } catch (e) {
        alert('Network error while cancelling');
      }
    }

    async function fetchSchedules() {
      try {
        const res = await fetch('/schedules');
        if (!res.ok) return;
        const schedules = await res.json();
        const tbody = document.getElementById('schedulesTableBody');

        if (!schedules.length) {
          tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-8 text-center text-slate-500">No recurring schedules configured.</td></tr>';
          return;
        }

        tbody.innerHTML = schedules.map(s => `
          <tr class="hover:bg-slate-850 transition">
            <td class="px-4 py-3 font-semibold text-slate-200">${s.name}</td>
            <td class="px-4 py-3 font-mono text-indigo-400">${s.cron_expression}</td>
            <td class="px-4 py-3 text-slate-300">${s.task_type}</td>
            <td class="px-4 py-3">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold ${s.enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-500/20 text-slate-400'}">${s.enabled ? 'ENABLED' : 'PAUSED'}</span>
            </td>
            <td class="px-4 py-3 text-slate-400">${s.last_run_at ? new Date(s.last_run_at).toLocaleString() : 'Never'}</td>
            <td class="px-4 py-3 text-slate-400">${s.next_run_at ? new Date(s.next_run_at).toLocaleString() : 'N/A'}</td>
          </tr>
        `).join('');
      } catch (err) {
        console.error('Failed to fetch schedules:', err);
      }
    }

    function openSubmitModal() {
      document.getElementById('submitModal').classList.remove('hidden');
    }

    function closeSubmitModal() {
      document.getElementById('submitModal').classList.add('hidden');
    }

    async function submitJob() {
      const task_type = document.getElementById('modalTaskType').value;
      const priority = document.getElementById('modalPriority').value;
      const max_retries = parseInt(document.getElementById('modalMaxRetries').value, 10);
      const timeout_seconds = parseInt(document.getElementById('modalTimeout').value, 10);
      let payload = {};

      try {
        payload = JSON.parse(document.getElementById('modalPayload').value);
      } catch (e) {
        alert('Invalid JSON in payload: ' + e.message);
        return;
      }

      const btn = document.getElementById('modalSubmitBtn');
      btn.disabled = true;
      btn.innerText = 'Submitting...';

      try {
        const res = await fetch('/jobs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_type, priority, payload, max_retries, timeout_seconds })
        });

        if (res.ok) {
          closeSubmitModal();
          fetchJobs();
          fetchStats();
        } else {
          const err = await res.json();
          alert('Submission failed: ' + (err.detail || 'Unknown error'));
        }
      } catch (e) {
        alert('Network error submitting job');
      } finally {
        btn.disabled = false;
        btn.innerText = 'Submit Job';
      }
    }

    // Initialize Dashboard on load
    window.onload = () => {
      fetchStats();
      fetchJobs();
      initWebSocket();
      setInterval(fetchStats, 5000);
    };
  </script>
</body>
</html>
"""

@router.get("/dashboard", response_class=HTMLResponse, summary="Operational Web Dashboard")
async def get_dashboard() -> HTMLResponse:
    """Returns the zero-dependency, self-contained operational dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)
