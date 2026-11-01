import sys
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def create_deck(output_path="Background_Job_System_Presentation.pptx"):
    prs = Presentation()
    # 16:9 widescreen dimensions
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Color Palette - Modern Tech Dark Theme
    COLOR_BG = RGBColor(15, 23, 42)        # Slate 900
    COLOR_CARD = RGBColor(30, 41, 59)      # Slate 800
    COLOR_CARD_BORDER = RGBColor(51, 65, 85) # Slate 700
    COLOR_CYAN = RGBColor(56, 189, 248)    # Sky 400
    COLOR_INDIGO = RGBColor(129, 140, 248) # Indigo 400
    COLOR_GREEN = RGBColor(52, 211, 153)   # Emerald 400
    COLOR_AMBER = RGBColor(251, 191, 36)   # Amber 400
    COLOR_RED = RGBColor(248, 113, 113)    # Red 400
    COLOR_WHITE = RGBColor(248, 250, 252)  # Slate 50
    COLOR_MUTED = RGBColor(148, 163, 184)  # Slate 400

    def add_background(slide):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = COLOR_BG
        bg.line.fill.background()
        return bg

    def add_header(slide, title_text, category_text="DISTRIBUTED SYSTEMS ARCHITECTURE"):
        # Category Tag
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.4))
        tf_cat = cat_box.text_frame
        tf_cat.word_wrap = True
        p_cat = tf_cat.paragraphs[0]
        p_cat.text = category_text.upper()
        p_cat.font.size = Pt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = COLOR_CYAN

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.7), Inches(0.8))
        tf_title = title_box.text_frame
        tf_title.word_wrap = True
        p_title = tf_title.paragraphs[0]
        p_title.text = title_text
        p_title.font.size = Pt(26)
        p_title.font.bold = True
        p_title.font.color.rgb = COLOR_WHITE

    def add_card(slide, left, top, width, height, title, items, badge="", accent_color=COLOR_CYAN):
        # Card Background
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_CARD
        card.line.color.rgb = COLOR_CARD_BORDER
        card.line.width = Pt(1.2)

        # Content Box
        padding = Inches(0.25)
        tb = slide.shapes.add_textbox(left + padding, top + padding * 0.7, width - (padding * 2), height - padding)
        tf = tb.text_frame
        tf.word_wrap = True

        # Header in Card
        p_head = tf.paragraphs[0]
        if badge:
            run_badge = p_head.add_run()
            run_badge.text = f"[{badge}] "
            run_badge.font.size = Pt(12)
            run_badge.font.bold = True
            run_badge.font.color.rgb = accent_color

        run_title = p_head.add_run()
        run_title.text = title
        run_title.font.size = Pt(15)
        run_title.font.bold = True
        run_title.font.color.rgb = COLOR_WHITE

        # Bullets / Details
        for item in items:
            p = tf.add_paragraph()
            p.font.size = Pt(12.5)
            p.font.color.rgb = COLOR_MUTED
            p.space_before = Pt(6)

            if isinstance(item, tuple):
                strong_part, rest = item
                r_strong = p.add_run()
                r_strong.text = "• " + strong_part + ": "
                r_strong.font.bold = True
                r_strong.font.color.rgb = COLOR_WHITE

                r_rest = p.add_run()
                r_rest.text = rest
                r_rest.font.color.rgb = COLOR_MUTED
            else:
                r = p.add_run()
                r.text = "• " + item
                r.font.color.rgb = COLOR_MUTED

    # -------------------------------------------------------------
    # SLIDE 1: TITLE SLIDE
    # -------------------------------------------------------------
    slide1 = prs.slides.add_slide(blank_layout)
    add_background(slide1)

    # Accent decorative bar
    bar = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.5), Inches(0.15), Inches(4.2))
    bar.fill.solid()
    bar.fill.fore_color.rgb = COLOR_CYAN
    bar.line.fill.background()

    t_box = slide1.shapes.add_textbox(Inches(1.6), Inches(1.4), Inches(10.5), Inches(4.5))
    tf1 = t_box.text_frame
    tf1.word_wrap = True

    p0 = tf1.paragraphs[0]
    p0.text = "ENTERPRISE DISTRIBUTED SYSTEMS"
    p0.font.size = Pt(13)
    p0.font.bold = True
    p0.font.color.rgb = COLOR_CYAN

    p1 = tf1.add_paragraph()
    p1.text = "Background Job Management System"
    p1.font.size = Pt(36)
    p1.font.bold = True
    p1.font.color.rgb = COLOR_WHITE
    p1.space_before = Pt(8)

    p2 = tf1.add_paragraph()
    p2.text = "A Failure-Resilient, High-Throughput Task Queue & Distributed Execution Engine"
    p2.font.size = Pt(18)
    p2.font.color.rgb = COLOR_INDIGO
    p2.space_before = Pt(12)

    p3 = tf1.add_paragraph()
    p3.text = "Transactional Outbox • Fencing Tokens • Weighted Fair Queues • Automated Lease Reaper"
    p3.font.size = Pt(13)
    p3.font.color.rgb = COLOR_MUTED
    p3.space_before = Pt(20)

    # Add quick pill badges at bottom
    badges = [
        ("PostgreSQL", COLOR_INDIGO),
        ("Redis 7+", COLOR_CYAN),
        ("FastAPI", COLOR_GREEN),
        ("React + TS", COLOR_AMBER),
        ("Prometheus & Grafana", COLOR_RED),
    ]
    badge_start_x = Inches(1.6)
    for name, col in badges:
        b_shape = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, badge_start_x, Inches(5.6), Inches(1.8), Inches(0.5))
        b_shape.fill.solid()
        b_shape.fill.fore_color.rgb = COLOR_CARD
        b_shape.line.color.rgb = col
        b_shape.line.width = Pt(1)
        b_tf = b_shape.text_frame
        b_tf.word_wrap = False
        bp = b_tf.paragraphs[0]
        bp.alignment = PP_ALIGN.CENTER
        bp.text = name
        bp.font.size = Pt(11)
        bp.font.bold = True
        bp.font.color.rgb = col
        badge_start_x += Inches(2.0)

    slide1.notes_slide.notes_text_frame.text = (
        "Welcome everyone. Today we are presenting the Background Job Management System — a resilient, "
        "production-grade distributed execution platform built to solve fundamental distributed systems failure modes: "
        "dual writes, zombie worker split brains, queue starvation, and unobservable background crashes."
    )

    # -------------------------------------------------------------
    # SLIDE 2: PROBLEM STATEMENT & MOTIVATION
    # -------------------------------------------------------------
    slide2 = prs.slides.add_slide(blank_layout)
    add_background(slide2)
    add_header(slide2, "The Problem: Why Traditional Queues Fail at Scale", "INDUSTRY CHALLENGES")

    add_card(slide2, Inches(0.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Dual-Write Divergence",
             [
                 ("Symptom", "Web service writes DB row, then crashes before enqueuing to Redis/RabbitMQ."),
                 ("Result", "Zombie database state. Job exists in DB but never gets picked up or processed."),
                 ("Flaw", "Naive microservices lack distributed transactions across heterogeneous databases.")
             ],
             badge="VULNERABILITY #1", accent_color=COLOR_RED)

    add_card(slide2, Inches(4.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Zombie Workers & Split Brain",
             [
                 ("Symptom", "Worker hits GC pause or network blip; coordinator presumes it dead and restarts task."),
                 ("Result", "Two workers execute simultaneously. The zombie finishes late and overwrites fresh state!"),
                 ("Flaw", "Lack of monotonic fencing tokens and atomic lease heartbeats.")
             ],
             badge="VULNERABILITY #2", accent_color=COLOR_AMBER)

    add_card(slide2, Inches(8.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Priority Starvation & Silent Failures",
             [
                 ("Symptom", "High-priority burst permanently starves default/low queues; unhandled exceptions vanish."),
                 ("Result", "Critical cron tasks delayed; poison pills endlessly loop, crashing worker nodes."),
                 ("Flaw", "Strict priority lacks fairness; missing Dead Letter Queue (DLQ) with audit trails.")
             ],
             badge="VULNERABILITY #3", accent_color=COLOR_CYAN)

    slide2.notes_slide.notes_text_frame.text = (
        "In many teams, background jobs are treated as an afterthought using naive Celery or BullMQ scripts. "
        "In reality, three catastrophic bugs routinely occur: dual-write loss during Redis outages, "
        "zombie workers overwriting updated database records, and starvation of background batch queues."
    )

    # -------------------------------------------------------------
    # SLIDE 3: ARCHITECTURAL BLUEPRINT (DUAL-ENGINE MODEL)
    # -------------------------------------------------------------
    slide3 = prs.slides.add_slide(blank_layout)
    add_background(slide3)
    add_header(slide3, "Core Architecture: The Dual-Engine Model", "SYSTEM DESIGN")

    add_card(slide3, Inches(0.8), Inches(1.7), Inches(5.6), Inches(4.8),
             "Durable Source of Truth (PostgreSQL)",
             [
                 ("ACID Storage", "Persists jobs, attempts, audit logs, and cron schedules."),
                 ("Conditional States", "Enforces valid lifecycle transitions via relational constraints."),
                 ("Audit Trail", "Every state change recorded into an append-only job_events table."),
                 ("Crash Immunity", "Even if Redis completely burns down, zero task definitions are lost."),
                 ("Query Engine", "Relational indexing for filtering, pagination, and administrative auditing.")
             ],
             badge="PERSISTENCE", accent_color=COLOR_INDIGO)

    add_card(slide3, Inches(6.8), Inches(1.7), Inches(5.6), Inches(4.8),
             "Transient Coordination Engine (Redis 7+)",
             [
                 ("Sub-Millisecond Dequeue", "In-memory priority queues for rapid worker dispatch."),
                 ("Lease Management", "TTL-backed worker leases renewed via asynchronous heartbeats."),
                 ("Rate Limiter", "Sliding window token buckets preventing downstream service saturation."),
                 ("Leader Locking", "Distributed mutex for single-leader cron schedule evaluation."),
                 ("Zero-Loss Recoverability", "Redis can be flushed and fully reconstructed from Postgres.")
             ],
             badge="COORDINATION", accent_color=COLOR_CYAN)

    slide3.notes_slide.notes_text_frame.text = (
        "Our architecture separates durable state from transient coordination. "
        "PostgreSQL acts as the single source of truth for jobs, execution logs, and audit trails. "
        "Redis handles ultra-fast atomic pops, worker leases, and distributed locks. "
        "If Redis fails, not a single byte of job data is lost."
    )

    # -------------------------------------------------------------
    # SLIDE 4: TRANSACTIONAL OUTBOX PATTERN
    # -------------------------------------------------------------
    slide4 = prs.slides.add_slide(blank_layout)
    add_background(slide4)
    add_header(slide4, "Transactional Outbox: Eliminating Dual Writes", "DATA INTEGRITY")

    add_card(slide4, Inches(0.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Step 1: Atomic Enqueue",
             [
                 ("Single Transaction", "FastAPI inserts Job record AND an OutboxEvent row in 1 atomic SQL transaction."),
                 ("Never Dual-Write", "The API never attempts to talk to Redis during the user HTTP request."),
                 ("Instant 201 Response", "Client receives immediate confirmation with guaranteed persistence.")
             ],
             badge="INGESTION", accent_color=COLOR_GREEN)

    add_card(slide4, Inches(4.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Step 2: Dedicated Publisher",
             [
                 ("Independent Process", "OutboxPublisher continuously polls uncommitted outbox rows with batching."),
                 ("Idempotent Redis Push", "Pushes job ID to appropriate Redis priority list (`high`, `default`, `low`)."),
                 ("Mark Published", "Sets `published_at = NOW()` in PostgreSQL upon Redis confirmation.")
             ],
             badge="DRAIN ENGINE", accent_color=COLOR_CYAN)

    add_card(slide4, Inches(8.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Step 3: Partition Resilience",
             [
                 ("Survives Outages", "If Redis is down for 30 minutes, incoming jobs safely buffer in PostgreSQL."),
                 ("Self-Healing Drain", "Once Redis recovers, publisher immediately drains backlog with zero data loss."),
                 ("Chaos Tested", "Fully verified through network partition simulation tests.")
             ],
             badge="CHAOS RESILIENT", accent_color=COLOR_AMBER)

    slide4.notes_slide.notes_text_frame.text = (
        "The Transactional Outbox pattern is one of our key resilience pillars. "
        "By writing the job and outbox event in the same ACID transaction, we decouple ingestion from Redis availability. "
        "Even during total Redis restarts or network partitions, ingestion never fails and no job is ever dropped."
    )

    # -------------------------------------------------------------
    # SLIDE 5: PRIORITY LANES & FAIR SCHEDULING
    # -------------------------------------------------------------
    slide5 = prs.slides.add_slide(blank_layout)
    add_background(slide5)
    add_header(slide5, "Priority Queues with 6:3:1 Weighted Fair Dequeuing", "FAIRNESS & QoS")

    add_card(slide5, Inches(0.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Tri-Lane Architecture",
             [
                 ("HIGH Priority", "For real-time critical events (e.g. password resets, security alerts)."),
                 ("DEFAULT Priority", "Standard workflows (e.g. notifications, report generation)."),
                 ("LOW Priority", "Batch processing (e.g. data syncs, telemetry compression).")
             ],
             badge="QUEUES", accent_color=COLOR_INDIGO)

    add_card(slide5, Inches(4.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "6:3:1 Weighted Scheduling",
             [
                 ("Weighted Sequence", "Workers dequeue in a weighted ratio: 6 High -> 3 Default -> 1 Low."),
                 ("Anti-Starvation", "Low-priority tasks are guaranteed execution bandwidth even under massive High bursts."),
                 ("Deterministic Cycle", "Maintains high throughput while strictly observing SLAs across classes.")
             ],
             badge="ALGORITHM", accent_color=COLOR_GREEN)

    add_card(slide5, Inches(8.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Atomic Lua Claiming",
             [
                 ("Zero Race Conditions", "Atomic pop and claim operations implemented via Redis Lua scripts."),
                 ("Competing Workers", "Multiple workers consume concurrently with zero duplicate claims."),
                 ("Queue Depth Telemetry", "Real-time depth tracking exposed through Prometheus and UI.")
             ],
             badge="ATOMICITY", accent_color=COLOR_CYAN)

    slide5.notes_slide.notes_text_frame.text = (
        "Standard priority queues suffer from starvation: a continuous flood of high-priority jobs blocks everything else. "
        "We implemented a 6:3:1 weighted fair scheduling algorithm. High priority gets 60% bandwidth, "
        "but Default gets 30% and Low is guaranteed 10%, completely eliminating starvation."
    )

    # -------------------------------------------------------------
    # SLIDE 6: WORKER ENGINE, LEASES & FENCING TOKENS
    # -------------------------------------------------------------
    slide6 = prs.slides.add_slide(blank_layout)
    add_background(slide6)
    add_header(slide6, "Worker Leases & Monotonic Fencing Tokens", "CONCURRENCY CONTROL")

    add_card(slide6, Inches(0.8), Inches(1.7), Inches(5.6), Inches(4.8),
             "Renewable Worker Leases",
             [
                 ("TTL-Backed Lease", "Worker acquires `lease:job:{id}` with 30s TTL in Redis upon claiming."),
                 ("Heartbeat Daemon", "Spawns background task renewing lease every TTL/3 (10s)."),
                 ("Worker Registration", "Records active worker ID, hostname, PID, and timestamp."),
                 ("Clean Shutdown", "Gracefully traps SIGTERM, allowing running jobs to finish within budget.")
             ],
             badge="LIVENESS", accent_color=COLOR_CYAN)

    add_card(slide6, Inches(6.8), Inches(1.7), Inches(5.6), Inches(4.8),
             "Monotonic Attempt Fencing",
             [
                 ("The Split-Brain Threat", "Zombie worker wakes up from pause and tries to record completed state."),
                 ("Fencing Token Guard", "Updates enforce `WHERE id = :id AND attempt_count = :attempt AND status = 'RUNNING'`."),
                 ("Rejection & Audit", "Stale write fails atomically; emits `ZOMBIE_WORKER_FENCED_OUT` event."),
                 ("Zero Overwrites", "Guarantees fresher attempts or reaper interventions are never corrupted.")
             ],
             badge="INTEGRITY", accent_color=COLOR_RED)

    slide6.notes_slide.notes_text_frame.text = (
        "This slide covers how we prevent the infamous zombie worker bug. "
        "Workers maintain a renewable lease with periodic heartbeats. "
        "Crucially, every database write is protected by a monotonic fencing token based on the attempt counter. "
        "If a zombie worker attempts to update a task after a lease timeout, PostgreSQL rejects the update and logs a fencing event."
    )

    # -------------------------------------------------------------
    # SLIDE 7: AUTOMATED LEASE REAPER & SELF-HEALING
    # -------------------------------------------------------------
    slide7 = prs.slides.add_slide(blank_layout)
    add_background(slide7)
    add_header(slide7, "Automated Lease Reaper: Self-Healing Crash Recovery", "HIGH AVAILABILITY")

    add_card(slide7, Inches(0.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Detection Loop",
             [
                 ("Active Daemon", "`LeaseReaper` background process audits RUNNING jobs periodically."),
                 ("Lease Verification", "Queries Redis for `lease:job:{id}`; if missing or expired, flags job."),
                 ("Heartbeat Check", "Cross-checks worker heartbeat to confirm worker termination or isolation.")
             ],
             badge="DETECTION", accent_color=COLOR_CYAN)

    add_card(slide7, Inches(4.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Safe Re-Queuing",
             [
                 ("Retry Evaluation", "If `attempt_count < max_retries`, transitions state back to `QUEUED`."),
                 ("Fenced State Update", "Atomic SQL CAS update prevents conflicts with late worker updates."),
                 ("Redis Re-Push", "Re-inserts job into priority queue for another worker to execute.")
             ],
             badge="RECOVERY", accent_color=COLOR_GREEN)

    add_card(slide7, Inches(8.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Terminal Dead-Lettering",
             [
                 ("Exhausted Attempts", "If retries are exhausted, marks job `DEAD` in PostgreSQL."),
                 ("Audit Trail", "Records `REAPER_ABANDONED_TASK` event with duration and worker info."),
                 ("Operator Alerting", "Increments Prometheus reaper recovery counter for alerting.")
             ],
             badge="DLQ TRANSFER", accent_color=COLOR_AMBER)

    slide7.notes_slide.notes_text_frame.text = (
        "What happens when a worker node hard-crashes (SIGKILL, hardware failure, out-of-memory)? "
        "Our Lease Reaper automatically detects jobs left in RUNNING status whose leases have lapsed. "
        "It uses optimistic concurrency to safely re-queue them or route them to the Dead Letter Queue without operator intervention."
    )

    # -------------------------------------------------------------
    # SLIDE 8: RETRY POLICY & DEAD-LETTER QUEUE (DLQ)
    # -------------------------------------------------------------
    slide8 = prs.slides.add_slide(blank_layout)
    add_background(slide8)
    add_header(slide8, "Exponential Backoff, Full Jitter & DLQ", "FAULT TOLERANCE")

    add_card(slide8, Inches(0.8), Inches(1.7), Inches(5.6), Inches(4.8),
             "Exponential Backoff with Full Jitter",
             [
                 ("Mathematical Model", "Delay = min(max_delay, base * 2^attempt) ± random_jitter."),
                 ("Prevents Thundering Herd", "Jitter desynchronizes retries against recovering downstream APIs."),
                 ("State Preservation", "Job enters `RETRY_WAIT` status with `scheduled_at = NOW() + delay`."),
                 ("Per-Job Customization", "Configurable base delay, multiplier, max delay, and max retries.")
             ],
             badge="BACKOFF ALGORITHM", accent_color=COLOR_INDIGO)

    add_card(slide8, Inches(6.8), Inches(1.7), Inches(5.6), Inches(4.8),
             "Dead Letter Queue (DLQ) & Operator Replay",
             [
                 ("Poison Pill Containment", "Permanently broken jobs transition to `DEAD` after retries expire."),
                 ("Diagnostic Context", "Captures full exception traceback, error type, attempt durations, and host."),
                 ("One-Click Replay", "Admin API `POST /jobs/{id}/retry` revives dead jobs with pristine history."),
                 ("No Lost Work", "Never discards failed jobs; fully queryable and filterable in dashboard.")
             ],
             badge="INSPECTION & REVIVAL", accent_color=COLOR_RED)

    slide8.notes_slide.notes_text_frame.text = (
        "Failed tasks are retried using exponential backoff with full jitter to avoid thundering herds against third-party APIs. "
        "When retries are exhausted, tasks are quarantined in the Dead Letter Queue. "
        "Operators have complete diagnostic context — stack trace, parameters, and attempt logs — and can replay jobs with a single click."
    )

    # -------------------------------------------------------------
    # SLIDE 9: DISTRIBUTED CRON & ADVANCED CONTROLS
    # -------------------------------------------------------------
    slide9 = prs.slides.add_slide(blank_layout)
    add_background(slide9)
    add_header(slide9, "Cron Scheduling, Rate Limiting & Cancellation", "WORKFLOW ENGINE")

    add_card(slide9, Inches(0.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Distributed Cron Scheduler",
             [
                 ("Leader Locking", "Redis-backed distributed lock ensures only 1 leader fires cron schedules."),
                 ("Timezone-Aware", "Native cron syntax with explicit timezone configuration via `croniter`."),
                 ("Child Job Spawning", "Schedules spawn standalone child jobs linked back to parent definition.")
             ],
             badge="AUTOMATION", accent_color=COLOR_CYAN)

    add_card(slide9, Inches(4.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Sliding-Window Rate Limiter",
             [
                 ("Token Bucket in Redis", "Protects rate-limited external APIs (Stripe, SendGrid, OpenAI)."),
                 ("Dynamic Delays", "Automatically defers jobs to `jobs:delayed` if rate limit threshold is breached."),
                 ("Zero Drops", "Smooths bursty workloads without rejecting submissions.")
             ],
             badge="TRAFFIC SHAPING", accent_color=COLOR_GREEN)

    add_card(slide9, Inches(8.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Cooperative Cancellation",
             [
                 ("API Cancellation", "Clients call `POST /jobs/{id}/cancel` to halt long-running tasks."),
                 ("Cancellation Tokens", "Handlers check `ctx.is_cancelled` during heavy iterative loops."),
                 ("Safe State Cleanup", "Guarantees intermediate resource cleanup (temp files, open sockets).")
             ],
             badge="GOVERNANCE", accent_color=COLOR_AMBER)

    slide9.notes_slide.notes_text_frame.text = (
        "Beyond ad-hoc jobs, the system supports recurring cron automation, sliding-window rate limiting, and cooperative cancellation. "
        "The scheduler uses a distributed leader lock so multiple instances can run without duplicate job triggers. "
        "Rate limiters protect third-party APIs, and cancellation tokens allow operators to abort runaway tasks cleanly."
    )

    # -------------------------------------------------------------
    # SLIDE 10: OBSERVABILITY & METRICS
    # -------------------------------------------------------------
    slide10 = prs.slides.add_slide(blank_layout)
    add_background(slide10)
    add_header(slide10, "Observability: Telemetry, Logs & Live WebSockets", "VISIBILITY")

    add_card(slide10, Inches(0.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Prometheus Metrics (`/metrics`)",
             [
                 ("Queue Depth Gauges", "`job_queue_depth{priority='high|default|low'}`."),
                 ("Execution Histograms", "`job_execution_duration_seconds` percentiles (p50, p95, p99)."),
                 ("Outcome Counters", "`job_executions_total{status='succeeded|failed|dead'}`."),
                 ("Grafana Ready", "Pre-configured dashboard JSON ready to import.")
             ],
             badge="METRICS", accent_color=COLOR_INDIGO)

    add_card(slide10, Inches(4.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Live WebSocket Stream (`/ws`)",
             [
                 ("Real-Time Broadcast", "Every state change immediately streamed to connected frontends."),
                 ("Zero Polling Load", "Eliminates repetitive database polling from client browsers."),
                 ("Instant Activity Feed", "Live ticker of job claims, completions, and retry attempts.")
             ],
             badge="REAL-TIME", accent_color=COLOR_CYAN)

    add_card(slide10, Inches(8.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Structured JSON Logging",
             [
                 ("Contextual Fields", "Injects `job_id`, `attempt_id`, `task_type`, `worker_id` into every log."),
                 ("ELK / Datadog Ready", "Machine-parseable JSON stdout output for log aggregators."),
                 ("Distributed Tracing", "Traceability from API ingestion down to worker handler execution.")
             ],
             badge="LOGGING", accent_color=COLOR_GREEN)

    slide10.notes_slide.notes_text_frame.text = (
        "Operational visibility is first-class. "
        "We export Prometheus metrics with pre-configured Grafana dashboards, broadcast live updates over WebSockets to eliminate database polling, "
        "and produce structured JSON logs with correlation IDs for ELK or Datadog ingestion."
    )

    # -------------------------------------------------------------
    # SLIDE 11: FULL-STACK INTERFACE & DASHBOARD
    # -------------------------------------------------------------
    slide11 = prs.slides.add_slide(blank_layout)
    add_background(slide11)
    add_header(slide11, "Full-Stack Control Plane & Administrative UI", "USER EXPERIENCE")

    add_card(slide11, Inches(0.8), Inches(1.7), Inches(5.6), Inches(4.8),
             "Built-in Zero-Dependency Dashboard (`/dashboard`)",
             [
                 ("Instant Ops Access", "Single lightweight HTML/JS interface embedded inside FastAPI."),
                 ("Zero Setup Required", "Accessible immediately on port 8000 without Node.js or bundlers."),
                 ("Core Controls", "Filter jobs, inspect attempts, view queue depths, and trigger retries.")
             ],
             badge="EMBEDDED UI", accent_color=COLOR_CYAN)

    add_card(slide11, Inches(6.8), Inches(1.7), Inches(5.6), Inches(4.8),
             "Modern React + TypeScript SPA (`frontend/`)",
             [
                 ("Component Architecture", "Modular UI built with React 18, Vite, and Tailwind CSS."),
                 ("Live WebSocket Hook", "Auto-reconnecting `useWebSocket` hook with optimistic UI updates."),
                 ("Rich Modals", "Submit Job Modal, Schedules Table, Worker Nodes View, and Attempt Inspector."),
                 ("Visual Depth Gauges", "Color-coded priority depth bars with real-time capacity gauges.")
             ],
             badge="ENTERPRISE SPA", accent_color=COLOR_AMBER)

    slide11.notes_slide.notes_text_frame.text = (
        "Operators get two dashboard experiences: "
        "First, a zero-dependency embedded dashboard accessible directly via GET /dashboard for rapid debugging without any build steps. "
        "Second, a full-featured React 18 and Tailwind SPA with live WebSocket streaming, visual queue depth gauges, and job management tools."
    )

    # -------------------------------------------------------------
    # SLIDE 12: VERIFICATION, TESTING & PRODUCTION READINESS
    # -------------------------------------------------------------
    slide12 = prs.slides.add_slide(blank_layout)
    add_background(slide12)
    add_header(slide12, "Verification, Benchmarks & Production Readiness", "RELIABILITY")

    add_card(slide12, Inches(0.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Automated Test Suite",
             [
                 ("Unit Tests", "State machine transitions, backoff math, schema validation, rate limiter."),
                 ("Integration Tests", "Transactional outbox drain, competing worker claiming, cron triggers."),
                 ("Chaos Tests", "Redis partition recovery, zombie worker fencing, lease expiration recovery.")
             ],
             badge="QUALITY ASSURANCE", accent_color=COLOR_GREEN)

    add_card(slide12, Inches(4.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Performance Benchmark",
             [
                 ("Concurrent Ingestion", "High-throughput asynchronous job ingestion via SQLAlchemy + asyncpg."),
                 ("Low-Latency Popping", "Lua-backed Redis dequeue with sub-millisecond dispatch."),
                 ("Horizontal Scaling", "Scale worker processes effortlessly across container clusters.")
             ],
             badge="PERFORMANCE", accent_color=COLOR_CYAN)

    add_card(slide12, Inches(8.8), Inches(1.7), Inches(3.6), Inches(4.8),
             "Deployment & Infrastructure",
             [
                 ("Docker Compose", "PostgreSQL 16, Redis 7, Prometheus, Grafana, and backend daemons."),
                 ("GitHub Actions CI", "Automated linting, type checks, and pytest integration pipeline."),
                 ("Production Ready", "Decoupled services, isolated failure domains, full audit logging.")
             ],
             badge="DEPLOYABILITY", accent_color=COLOR_INDIGO)

    slide12.notes_slide.notes_text_frame.text = (
        "In conclusion, this project provides a battle-tested foundation for background processing. "
        "Every distributed failure scenario — network partitions, node crashes, split-brain zombies, and traffic spikes — "
        "has been designed for and validated with automated integration and chaos tests. Thank you!"
    )

    # Save presentation
    prs.save(output_path)
    print(f"Presentation saved successfully to: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "Background_Job_System_Presentation.pptx"
    create_deck(out_file)
