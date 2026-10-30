"""Optimization loop: lowest mass with Von Mises below the limit (COBYLA)."""
import numpy as np
from scipy.optimize import minimize

from optimizer.evaluation import OK, OK_CHECK

MAX_INVALID_IN_A_ROW = 3
INITIAL_STEP = 0.25  # fraction of each parameter's range


STOP_CONVERGED = "converged"
STOP_MAX_ITERATIONS = "max_iterations"
STOP_REQUESTED = "requested"
STOP_INVALID = "invalid"

STOP_MESSAGES = {
    STOP_CONVERGED: "The optimizer converged: the steps became too small to improve the part.",
    STOP_MAX_ITERATIONS: "Stopped at the maximum number of iterations (max_iterations = %d).",
    STOP_REQUESTED: "Stop requested by the user; the best result so far was saved.",
    STOP_INVALID: "Stopped: %d invalid iterations in a row (see the reasons above)." % MAX_INVALID_IN_A_ROW,
}


def stop_message(reason, settings):
    message = STOP_MESSAGES[reason]
    return message % settings.max_iterations if reason == STOP_MAX_ITERATIONS else message


class BaselineError(Exception):
    """The part with its current values could not be evaluated."""


class _Stop(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def choose_best(history):
    """Lightest among 'OK ✓'; otherwise lightest among 'OK ⚠'; otherwise the lowest stress."""
    for status in (OK, OK_CHECK):
        candidates = [it for it in history if it.status == status]
        if candidates:
            return min(candidates, key=lambda it: it.mass_kg)
    valid = [it for it in history if it.valid]
    return min(valid, key=lambda it: it.von_mises) if valid else None


def optimize(evaluate, settings, on_iteration, should_stop):
    params = settings.parameters
    minimums = np.array([p.minimum for p in params])
    ranges = np.array([p.maximum - p.minimum for p in params])
    limit = settings.stress_limit
    history, cache = [], {}
    state = {"best": None, "invalid": 0, "max_mass": 0.0}

    def run(x):
        x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
        key = tuple(np.round(x, 6))
        if key in cache:
            return cache[key]
        if len(history) >= settings.max_iterations:
            raise _Stop(STOP_MAX_ITERATIONS)
        if history and should_stop():
            raise _Stop(STOP_REQUESTED)
        values = {p.alias: float(v) for p, v in zip(params, minimums + x * ranges)}
        it = evaluate(values)
        history.append(it)
        cache[key] = it
        best = choose_best(history)
        is_best = best is it
        state["best"] = best
        on_iteration(it, is_best)
        if it.valid:
            state["invalid"] = 0
            state["max_mass"] = max(state["max_mass"], it.mass_kg)
        else:
            state["invalid"] += 1
            if len(history) > 1 and state["invalid"] >= MAX_INVALID_IN_A_ROW:
                raise _Stop(STOP_INVALID)
        return it

    x0 = np.array([(p.value - p.minimum) / (p.maximum - p.minimum) for p in params])
    base = run(x0)
    if not base.valid:
        raise BaselineError(base.reason)

    def objective(x):
        it = run(x)
        return it.mass_kg if it.valid else state["max_mass"]

    def margin(x):
        it = run(x)
        return (limit - it.von_mises) / limit if it.valid else -1.0

    # COBYLA tries x0 ± step; starting at a bound, those points would fall outside the
    # range, be clipped back to the baseline and the step would shrink until it vanished.
    start = np.clip(x0, INITIAL_STEP, 1.0 - INITIAL_STEP)
    reason = STOP_CONVERGED
    try:
        minimize(objective, start, method="COBYLA", bounds=[(0.0, 1.0)] * len(params),
                 constraints=[{"type": "ineq", "fun": margin}],
                 options={"maxiter": 10 * settings.max_iterations, "rhobeg": INITIAL_STEP})
    except _Stop as stop:
        reason = stop.reason
    return choose_best(history), history, reason
