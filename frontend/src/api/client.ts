import { Job, JobListResponse, Schedule, SystemStats } from '../types';

const BASE_URL = '';

export async function fetchStats(): Promise<SystemStats> {
  const res = await fetch(`${BASE_URL}/stats`);
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.statusText}`);
  return res.json();
}

export async function fetchJobs(
  status?: string,
  priority?: string,
  page: number = 1,
  pageSize: number = 25
): Promise<JobListResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  });
  if (status) params.append('status', status);
  if (priority) params.append('priority', priority);

  const res = await fetch(`${BASE_URL}/jobs?${params.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.statusText}`);
  return res.json();
}

export async function fetchJobById(id: string): Promise<Job> {
  const res = await fetch(`${BASE_URL}/jobs/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch job ${id}: ${res.statusText}`);
  return res.json();
}

export async function createJob(data: {
  task_type: string;
  payload: Record<string, any>;
  priority?: string;
  max_retries?: number;
  timeout_seconds?: number;
  idempotency_key?: string;
}): Promise<Job> {
  const res = await fetch(`${BASE_URL}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to create job: ${res.statusText}`);
  }
  return res.json();
}

export async function retryJob(id: string): Promise<Job> {
  const res = await fetch(`${BASE_URL}/jobs/${id}/retry`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to retry job: ${res.statusText}`);
  }
  return res.json();
}

export async function cancelJob(id: string): Promise<Job> {
  const res = await fetch(`${BASE_URL}/jobs/${id}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to cancel job: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSchedules(): Promise<Schedule[]> {
  const res = await fetch(`${BASE_URL}/schedules`);
  if (!res.ok) throw new Error(`Failed to fetch schedules: ${res.statusText}`);
  return res.json();
}

export async function updateSchedule(id: string, updates: Partial<Schedule>): Promise<Schedule> {
  const res = await fetch(`${BASE_URL}/schedules/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Failed to update schedule: ${res.statusText}`);
  return res.json();
}

export async function deleteSchedule(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/schedules/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete schedule: ${res.statusText}`);
}
