from concurrent.futures import ThreadPoolExecutor


def fan_out(jobs, worker, max_workers=4):
    results = []
    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(jobs)))) as pool:
        futures = [(job, pool.submit(worker, job)) for job in jobs]
        for job, future in futures:
            try:
                results.append({"job": job, "ok": True, "result": future.result()})
            except Exception as error:
                results.append({"job": job, "ok": False, "error": f"{type(error).__name__}: {error}"})
    return results


def chain(value, steps):
    trace = []
    for step in steps:
        value = step(value)
        trace.append(value)
    return value, trace
