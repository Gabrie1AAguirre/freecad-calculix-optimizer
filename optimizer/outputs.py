"""Optimization outputs: CSV history, terminal lines, chart and summary."""
import csv

from optimizer.evaluation import OK, OK_CHECK

FIXED_COLUMNS = ["von_mises_mpa", "von_mises_raw_mpa", "max_location", "mass_kg", "status", "reason"]
VM_WIDTH = 12
MASS_WIDTH = 9


def _csv_number(value):
    """Number for the CSV; empty if None."""
    return "" if value is None else "%.6g" % value


class History:
    """CSV with one row per iteration (UTF-8 with BOM so Excel shows ✓ and ⚠).
    Each row is written immediately."""

    def __init__(self, csv_path, aliases):
        self.path = csv_path
        self.aliases = list(aliases)
        with open(self.path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(["iteration"] + self.aliases + FIXED_COLUMNS)

    def add(self, it):
        location = "" if it.location is None else "%.1f %.1f %.1f" % tuple(it.location)
        row = ([str(it.number)] + [_csv_number(it.values.get(a)) for a in self.aliases]
               + [_csv_number(it.von_mises), _csv_number(it.von_mises_raw), location,
                  _csv_number(it.mass_kg), it.status, it.reason])
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(row)


def _width(alias):
    return max(len(alias), 8)


def terminal_header(aliases):
    parts = ["iter"] + [a.rjust(_width(a)) for a in aliases]
    parts += ["VonMises_max".rjust(VM_WIDTH), "mass".rjust(MASS_WIDTH), "  status"]
    return "  ".join(parts)


def terminal_line(it, aliases, is_best):
    parts = ["%4d" % it.number] + [("%.1f" % it.values[a]).rjust(_width(a)) for a in aliases]
    vm = "" if it.von_mises is None else "%.0f MPa" % it.von_mises
    mass = "" if it.mass_kg is None else "%.2f kg" % it.mass_kg
    parts += [vm.rjust(VM_WIDTH), mass.rjust(MASS_WIDTH)]
    status = "  " + it.status
    if is_best:
        status += " best so far" if it.status in (OK, OK_CHECK) else " (lowest stress so far)"
    if it.reason:
        status += " — " + it.reason
    return "  ".join(parts + [status])


def make_chart(history, limit, png_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    valid = [it for it in history if it.valid]
    fig, (vm_axis, mass_axis) = plt.subplots(2, 1, sharex=True, figsize=(8, 6))
    colors = {OK: "tab:green", OK_CHECK: "tab:orange"}
    vm_axis.plot([it.number for it in valid], [it.von_mises for it in valid], color="0.6", zorder=1)
    vm_axis.scatter([it.number for it in valid], [it.von_mises for it in valid],
                    c=[colors.get(it.status, "tab:red") for it in valid], zorder=2)
    vm_axis.axhline(limit, color="tab:red", linestyle="--", label="limit %.0f MPa" % limit)
    vm_axis.set_ylabel("Max. Von Mises (MPa)")
    vm_axis.legend()
    mass_axis.plot([it.number for it in valid], [it.mass_kg for it in valid], marker="o")
    mass_axis.set_ylabel("Mass (kg)")
    mass_axis.set_xlabel("Iteration")
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    plt.close(fig)


def summary(base, best, limit):
    if best is None:
        return "No valid iteration: there is no result to deliver."
    change = 100.0 * (best.mass_kg - base.mass_kg) / base.mass_kg
    lines = [
        "Baseline: %.0f MPa, %.2f kg" % (base.von_mises, base.mass_kg),
        "Best: iteration %d — %.0f MPa, %.2f kg (%+.1f%% mass)"
        % (best.number, best.von_mises, best.mass_kg, change),
        "Values: " + ", ".join("%s = %.2f" % kv for kv in best.values.items()),
    ]
    if best.status == OK:
        lines.append("✓ The optimization reached the %.0f MPa limit." % limit)
    elif best.status == OK_CHECK:
        lines.append("⚠ The optimization reached the %.0f MPa limit, but it needs checking: %s"
                     % (limit, best.reason))
    else:
        lines.append("✗ The optimization did not reach the %.0f MPa limit within the parameter ranges; "
                     "this is the combination with the lowest stress. Widen the ranges or revise the design."
                     % limit)
    return "\n".join(lines)
