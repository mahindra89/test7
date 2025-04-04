import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.colors as mcolors
import pandas as pd
import random

# Title
st.title("STRF Scheduling (with quantum time)")

# --- Top Input Row: Number of Jobs, CPUs, Chunk Unit, Quantum Time ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    num_jobs = st.number_input("Number of Jobs", min_value=1, max_value=10, value=4)
with col2:
    num_cpus = st.number_input("Number of CPUs", min_value=1, max_value=4, value=2)
with col3:
    chunk_unit = st.number_input("Chunk Unit (e.g., 0.5, 1.0):", value=1.0)
with col4:
    quantum_time = st.number_input("Quantum Time:", value=2.0)

# Random values setup
def get_random_half_step(min_val, max_val):
    steps = int((max_val - min_val) * 2) + 1
    return round(min_val + 0.5 * random.randint(0, steps - 1), 1)

if 'random_values' not in st.session_state:
    st.session_state.random_values = []

if st.button("Randomize Job Times"):
    st.session_state.random_values = [
        {'arrival': get_random_half_step(0, 5), 'burst': get_random_half_step(1, 10)}
        for _ in range(num_jobs)
    ]

# Job Inputs
processes = []
for i in range(num_jobs):
    st.subheader(f"Job J{i+1}")
    default_arrival = st.session_state.random_values[i]['arrival'] if i < len(st.session_state.random_values) else 0.0
    default_burst = st.session_state.random_values[i]['burst'] if i < len(st.session_state.random_values) else 3.0

    c1, c2 = st.columns(2)
    with c1:
        arrival = st.number_input(f"Arrival Time for J{i+1}", value=default_arrival, key=f"arrival_{i}")
    with c2:
        burst = st.number_input(f"Burst Time for J{i+1}", value=default_burst, key=f"burst_{i}")
    processes.append({'id': f'J{i+1}', 'arrival_time': arrival, 'burst_time': burst})

# Simulation trigger
if st.button("Run Special STRF"):
    arrival_time = {p['id']: p['arrival_time'] for p in processes}
    burst_time = {p['id']: p['burst_time'] for p in processes}
    remaining_time = burst_time.copy()
    start_time, end_time, job_chunks = {}, {}, {}

    for job_id, total in burst_time.items():
        chunks = []
        remaining = total
        while remaining > 0:
            chunk = min(chunk_unit, remaining)
            chunks.append(chunk)
            remaining -= chunk
        job_chunks[job_id] = chunks

    cpu_names = [f"CPU{i+1}" for i in range(num_cpus)]
    busy_until = {cpu: 0 for cpu in cpu_names}
    current_jobs = {cpu: None for cpu in cpu_names}
    busy_jobs = set()
    gantt_data, queue_snapshots = [], []
    current_time = 0
    jobs_completed = 0
    next_scheduling_time = 0

    def capture_queue_state(time, available_jobs):
        queue = sorted(
            [j for j in available_jobs if remaining_time[j] > 0],
            key=lambda j: (remaining_time[j], arrival_time[j])
        )
        if queue:
            job_info = [(j, round(remaining_time[j], 1)) for j in queue]
            queue_snapshots.append((time, job_info))

    initial_available = [p['id'] for p in processes if p['arrival_time'] <= current_time]
    capture_queue_state(current_time, initial_available)

    while jobs_completed < len(processes):
        for cpu in cpu_names:
            if busy_until[cpu] <= current_time and current_jobs[cpu]:
                job_id = current_jobs[cpu]
                busy_jobs.discard(job_id)
                current_jobs[cpu] = None

        can_schedule = current_time >= next_scheduling_time
        available_cpus = [cpu for cpu in cpu_names if busy_until[cpu] <= current_time and current_jobs[cpu] is None]
        available_jobs = [j for j in remaining_time if remaining_time[j] > 0 and arrival_time[j] <= current_time and j not in busy_jobs]

        if can_schedule and available_cpus and available_jobs:
            capture_queue_state(current_time, available_jobs)
            available_jobs.sort(key=lambda j: (remaining_time[j], arrival_time[j]))

            for cpu in available_cpus:
                if not available_jobs:
                    break
                job = available_jobs.pop(0)
                chunk = job_chunks[job].pop(0)
                if job not in start_time:
                    start_time[job] = current_time
                busy_jobs.add(job)
                current_jobs[cpu] = job
                remaining_time[job] -= chunk
                busy_until[cpu] = current_time + chunk
                gantt_data.append((current_time, cpu, job, chunk))
                if remaining_time[job] < 1e-3:
                    end_time[job] = current_time + chunk
                    jobs_completed += 1
            next_scheduling_time = current_time + quantum_time

        next_events = [busy_until[c] for c in cpu_names if busy_until[c] > current_time]
        next_events += [arrival_time[j] for j in arrival_time if arrival_time[j] > current_time and remaining_time[j] > 0]
        if next_scheduling_time > current_time:
            next_events.append(next_scheduling_time)
        current_time = min(next_events) if next_events else current_time + 0.1

    for p in processes:
        p['start_time'] = start_time[p['id']]
        p['end_time'] = end_time[p['id']]
        p['turnaround_time'] = p['end_time'] - p['arrival_time']

    df = pd.DataFrame([{
        "Job": p['id'],
        "Arrival": p['arrival_time'],
        "Burst": p['burst_time'],
        "Start": round(p['start_time'], 1),
        "End": round(p['end_time'], 1),
        "Turnaround": round(p['turnaround_time'], 1)
    } for p in processes])
    avg_turnaround = sum(p['turnaround_time'] for p in processes) / len(processes)

    st.subheader("Result Table")
    st.dataframe(df, use_container_width=True)
    st.markdown(f"**Average Turnaround Time:** `{avg_turnaround:.2f}`")

    # Gantt Chart
    def draw_gantt(gantt_data, queue_snapshots):
        max_time = max(end_time.values())
        fig, ax = plt.subplots(figsize=(18, 8))
        cmap = plt.colormaps.get_cmap('tab20')
        colors = {f'J{i+1}': mcolors.to_hex(cmap(i / max(len(processes), 1))) for i in range(len(processes))}
        cpu_ypos = {cpu: num_cpus - idx for idx, cpu in enumerate(cpu_names)}

        for start, cpu, job, duration in gantt_data:
            y = cpu_ypos[cpu]
            ax.barh(y, duration, left=start, color=colors[job], edgecolor='black')
            ax.text(start + duration / 2, y, job, ha='center', va='center', color='white', fontsize=9)

        for t in range(int(max_time) + 1):
            if t % int(quantum_time) == 0:
                ax.axvline(x=t, color='red', linestyle='-', linewidth=0.5, alpha=0.6)
            else:
                ax.axvline(x=t, color='black', linestyle='--', alpha=0.2)

        queue_y_base = -1
        for time, jobs in queue_snapshots:
            for i, (jid, rem) in enumerate(jobs):
                y = queue_y_base - i * 0.6
                rect = patches.Rectangle((time - 0.25, y - 0.25), 0.5, 0.5, edgecolor='black', facecolor='white')
                ax.add_patch(rect)
                ax.text(time, y, f"{jid}={rem}", ha='center', va='center', fontsize=7)

        if queue_snapshots:
            max_q = max(len(q[1]) for q in queue_snapshots)
            ax.set_ylim(-1 - max_q * 0.6 - 0.5, num_cpus + 1)

        ax.set_yticks(list(cpu_ypos.values()))
        ax.set_yticklabels(cpu_ypos.keys())
        ax.set_xlabel("Time (seconds)")
        ax.set_title("STRF Gantt Chart with Quantum Scheduling")
        ax.legend([patches.Patch(color='red', label='Quantum Markers')])
        plt.grid(axis='x')
        plt.tight_layout()
        return fig

    st.subheader("Gantt Chart")
    st.pyplot(draw_gantt(gantt_data, queue_snapshots), use_container_width=True)
