#!/usr/bin/env python3
"""Run a command; print wall, user+sys CPU of all waited children, max single-process RSS and cgroup peak."""
import json, resource, subprocess, sys, time
t = time.perf_counter()
p = subprocess.run(sys.argv[1:])
w = time.perf_counter() - t
r = resource.getrusage(resource.RUSAGE_CHILDREN)
peak = None
for f in ("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"):
    try:
        peak = int(open(f).read()); break
    except Exception:
        pass
print("MEASURE " + json.dumps({"rc": p.returncode, "wall_s": round(w, 1), "cpu_s": round(r.ru_utime + r.ru_stime, 1),
      "max_proc_rss_mb": round(r.ru_maxrss / 1024), "cgroup_peak_mb": None if peak is None else round(peak / 1048576)}))
