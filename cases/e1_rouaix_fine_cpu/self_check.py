"""Small offline checks; no Docker, mesh generation, or CFD."""

from pathlib import Path

from run_pilot import PATCHES, SOLVER_SHELL, docker, integrate_sample, replace_entry

source = Path(__file__).with_name("run_pilot.py").read_text()
capacity_wait = source[
    source.index("    while True:\n        active = []") : source.index("    cmd = docker(")
]
assert (
    capacity_wait.index('if (run / "PAUSE")')
    < capacity_wait.index("if time.time() >= deadline:")
    < capacity_wait.index("if not active and busy < 1:")
)

assert replace_entry("endTime 1;", "endTime", "0.002") == "endTime 0.002;"
try:
    replace_entry("x 1;", "missing", "2")
except ValueError:
    pass
else:
    raise AssertionError("missing dictionary key accepted")

command = docker(Path("/case"), "test", SOLVER_SHELL)
assert "--cpus=20" in command and "--memory=88g" in command
assert "--memory-swap=88g" in command and "--gpus" not in command
assert command[-1].endswith(SOLVER_SHELL) and "interIsoFoam -help && mpirun" in command[-1]
flux = dict.fromkeys(PATCHES, 0.0)
flux.update(nozzle=-2.0, downstreamOutlet=0.5)
sample = {"alpha_phi": flux, "inventory_m3": 0.15}
injected, external = integrate_sample(0.1, 0, sample, 0, 0)
assert abs(injected - 0.2) < 1e-15 and abs(external - 0.05) < 1e-15
assert abs(sample["residual_m3"]) < 1e-15
for bad in ({"alpha_phi": {}}, {"alpha_phi": flux, "inventory_m3": float("nan")}):
    try:
        integrate_sample(0.1, 0, bad, 0, 0)
    except ValueError:
        pass
    else:
        raise AssertionError("incomplete/nonfinite sample accepted")
print("fine pilot dictionary, resources and native-ledger self-checks passed")
