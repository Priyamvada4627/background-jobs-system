export type JobStatus = 
  | 'QUEUED' 
  | 'RUNNING' 
  | 'SUCCEEDED' 
  | 'RETRY_WAIT' 
  | 'DEAD' 
  | 'CANCELLED';

export type JobPriority = 'HIGH' | 'DEFAULT' | 'LOW';

export interface JobAttempt {
  id: string;
  job_id: string;
  attempt_number: number;
  worker_id: string;
  started_at: string;
  finished_at: string;
  outcome: 'SUCCEEDED' | 'FAILED' | 'TIMED_OUT' | 'CANCELLED';
  error_type?: string | null;
  error_message?: string | null;
  traceback_text?: string | null;
  duration_ms: number;
}

export interface Job {
  id: string;
  task_type: string;
  payload: Record<string, any>;
  status: JobStatus;
  priority: JobPriority;
  idempotency_key?: string | null;
  scheduled_at: string;
  max_retries: number;
  attempt_count: number;
  timeout_seconds: number;
  last_error?: string | null;
  result?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
  attempts?: JobAttempt[];
}

export interface JobListResponse {
  items: Job[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface Schedule {
  id: string;
  name: string;
  cron_expression: string;
  timezone: string;
  task_type: string;
  payload: Record<string, any>;
  priority: JobPriority;
  max_retries: number;
  timeout_seconds: number;
  enabled: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Worker {
  worker_id: string;
  hostname: string;
  pid: number;
  started_at?: string | null;
  last_heartbeat_at?: string | null;
  current_job_id?: string | null;
  capabilities?: Record<string, any>;
}

export interface SystemStats {
  queue_depths: {
    HIGH: number;
    DEFAULT: number;
    LOW: number;
    TOTAL: number;
  };
  jobs_by_status: {
    QUEUED: number;
    RUNNING: number;
    SUCCEEDED: number;
    RETRY_WAIT: number;
    DEAD: number;
    CANCELLED: number;
    TOTAL: number;
  };
  active_workers_count: number;
  active_workers: Worker[];
  enabled_schedules_count: number;
}

export interface WSEvent {
  event: string;
  data: Record<string, any>;
  timestamp?: string;
}
