# 3dxpy (`pycatia3dx`)

Unified Python automation library for the **Dassault Systèmes 3DEXPERIENCE** ecosystem — covering **CATIA**, **SIMULIA** (both in-client `sma_*` / `sim_*` / `fmt_mode` simulation and standalone/embedded solvers including **Abaqus**, **Isight**, **Tosca**, **fe-safe**, **Simpack**, **CST Studio Suite**, **PowerFLOW**, **XFlow**, and **Wave6**), **DELMIA**, **ENOVIA / 3DSpace / 3DPassport / 3DSearch / 3DSwym** REST APIs, **BIOVIA**, **GEOVIA**, **3DEXCITE**, **SOLIDWORKS**, and headless **CATIA Batch / `CATSTART`** utilities.

Works out-of-the-box on any 3DEXPERIENCE UI language (English, French, German, Spanish, Italian, Japanese, Chinese, Korean, etc.) and Python 3.11–3.14 without modifying any files inside the Dassault Systèmes installation.

---

## Requirements

- **Python** `>= 3.11` (3.11 – 3.14 supported)
- **Windows** + `pywin32 >= 306`, `psutil >= 5.9` for live 3DEXPERIENCE rich-client COM automation
- Standalone SIMULIA drivers (`AbaqusRunner`, `AbaqusInpDeck`, `AbaqusOdbReader`, `ToscaRunner`, `IsightRunner`, `FeSafeRunner`, etc.) and `ThreeDXPlatformClient` REST APIs run on **both Windows and Linux** with **zero external runtime dependencies**.

```bash
python -m pip install -e .
```

---

## Quick Start — Unified `ThreeDExperience` Hub

```python
from pycatia3dx import ThreeDExperience

dx = ThreeDExperience()

# Inspect local 3DEXPERIENCE releases, CATEnv files, and solver binaries
print(dx.discover())
```

---

## 1. SIMULIA & Abaqus Automation

### A. Build or Modify Abaqus `.inp` Input Decks in Pure Python

```python
from pycatia3dx import AbaqusInpDeck

deck = AbaqusInpDeck(heading="Cantilever Bracket Static Analysis")
deck.add_nodes({1: (0, 0, 0), 2: (100, 0, 0), 3: (100, 20, 0), 4: (0, 20, 0)})
deck.add_elements("CPS4R", {1: (1, 2, 3, 4)}, elset="ALL_ELS")
deck.add_nset("FIXED", [1, 4])
deck.add_nset("TIP", [2, 3])
deck.add_isotropic_material("STEEL", youngs_modulus=210000.0, poissons_ratio=0.3, density=7.85e-9)
deck.add_solid_section("ALL_ELS", "STEEL", thickness=5.0)
deck.add_static_step(
    name="TipLoad",
    boundaries=[("FIXED", 1, 2, 0.0)],
    cloads=[("TIP", 2, -1500.0)],
)
deck.write("cantilever.inp")
```

### B. Run Standalone or 3DEXPERIENCE-Embedded Abaqus Solver Jobs

```python
from pycatia3dx import AbaqusRunner

abq = AbaqusRunner()  # Auto-discovers abaqus / abq202x / ABQLauncher / SMALauncher
result = abq.run_job("cantilever_job", input_file="cantilever.inp", cpus=4, interactive=True)

print(result.job_status.completed)          # True
print(len(result.job_status.increments))    # Parsed from .sta
print(result.job_status.warnings)           # Parsed from .msg / .dat
```

### C. Drive Abaqus's Own Python (`mdb`, `session`, `odbAccess`) Inline from Modern Python

```python
def create_part_in_abaqus_cae(payload):
    from abaqus import mdb
    model = mdb.models["Model-1"]
    sketch = model.ConstrainedSketch(name="rect", sheetSize=200.0)
    sketch.rectangle(point1=(0.0, 0.0), point2=(payload["w"], payload["h"]))
    part = model.Part(name="Plate", dimensionality=3, type=1)
    part.BaseSolidExtrude(sketch=sketch, depth=payload["thickness"])
    mdb.saveAs(pathName=payload["cae_file"])
    return {"parts": list(model.parts.keys())}

res = abq.execute_inline(
    create_part_in_abaqus_cae,
    {"w": 80.0, "h": 40.0, "thickness": 6.0, "cae_file": "plate.cae"},
    mode="cae",  # Runs `abaqus cae noGUI=...` and marshals JSON back
)
print(res.output_data)
```

### D. Extract Stress, Displacement, & History Data from `.odb` Files

```python
from pycatia3dx import AbaqusOdbReader

odb = AbaqusOdbReader("cantilever_job.odb", runner=abq)
print(odb.inspect())

stress = odb.read_field_output("S", step="TipLoad", frame=-1)
print("Max von Mises:", stress["max_mises"])
odb.export_field_to_csv("cantilever_stress.csv", "S")
```

### E. Other SIMULIA Solvers (Tosca, Isight, fe-safe, Simpack, CST, PowerFLOW, XFlow, Wave6)

```python
# Topology Optimization with SIMULIA Tosca
par_text = dx.simulia.tosca.build_topology_par(
    fem_input="cantilever.inp",
    design_elset="ALL_ELS",
    volume_fraction=0.30,
)
open("topo.par", "w").write(par_text)
dx.simulia.tosca.run_optimization("topo.par", solver="abaqus", cpus=4)

# Process Workflow with SIMULIA Isight / SEE
dx.simulia.isight.run_workflow("doe_study.zmf", parameters={"thickness": 6.0})

# Fatigue Durability with SIMULIA fe-safe
macro = dx.simulia.fesafe.build_fatigue_macro(input_odb="cantilever_job.odb", output_odb="life.odb")
open("fatigue.macro", "w").write(macro)
dx.simulia.fesafe.run_macro("fatigue.macro")

# Multibody Dynamics with SIMULIA Simpack
dx.simulia.simpack.run_time_integration("suspension.spck", cpus=4)

# Electromagnetics with SIMULIA CST Studio Suite (COM or Headless Batch)
dx.simulia.cst.run_batch_solver("antenna.cst", solver_flag="-f", gpus=1)
```

### F. In-Client SIMULIA Automation (`sma_*`, `sim_*`, `fmt_mode`)

```python
# Create and execute a Multiphysics Structural Simulation inside the 3DEXPERIENCE client
sim_ref, sim_editor = dx.simulia.client.create_simulation("Bracket_FEA", product_entity)
dx.simulia.client.execute_all_cases(sim_ref)
```

---

## 2. CATIA, DELMIA, Universal Rich-Client COM, & Other Brands

```python
# Connect to active 3DEXPERIENCE rich client
app = dx.catia

# Switch workbenches across CATIA, SIMULIA, DELMIA, or ENOVIA
dx.client.switch_workbench(dx.workbenches.PART_DESIGN)

# Access ANY session or editor service — static wrapper if registered, or DynamicCOMService automatically!
svc = app.get_session_service("PLMNewService")
custom_svc = app.get_session_service("AnyCustomRoleService")

# Run inline VBScript inside 3DEXPERIENCE and return values to Python
title = dx.client.run_inline_vbscript("RESULT = CATIA.Caption")

# DELMIA Robotics Offline Programming (FANUC / KUKA / ABB / Yaskawa)
dx.delmia.download_robot_programs(robot_occ, [weld_task], "./robot_programs", translator="DELMIA Fanuc Translator")

# CATIA / 3DEXPERIENCE Headless Batch & CATSTART CLI
dx.batch.run_cad_translation_batch(["assembly.3dxml"], "./step_out", target_format="STEP")

# BIOVIA, GEOVIA, 3DEXCITE, & SOLIDWORKS
dx.biovia.run_pipeline_pilot_protocol("Protocols/QSAR_Model", parameters={"Threshold": 0.85})
dx.geovia.run_surpac_macro("block_model.tcl")
dx.excite.render_scene_batch("car_studio.csb", headless=True)
sw_doc = dx.solidworks.open_doc("housing.SLDPRT")
```

---

## 3. ENOVIA / 3DSpace / 3DPassport / 3DSearch / 3DSwym REST API

```python
plm = dx.platform(
    space_url="https://your-tenant-space.3dexperience.3ds.com/enovia",
    passport_url="https://eu1-authn.3dexperience.3ds.com",
    search_url="https://your-tenant-search.3dexperience.3ds.com/federated",
    tenant="R1132100000000",
)

# Authenticate via 3DPassport CAS, API token, or Basic Auth
plm.login_3dpassport("user@example.com", "password")
plm.discover_security_contexts()  # Auto-populates Role.Organization.CollabSpace

# Search, create, BOM-expand, and transition maturity states in 3DSpace
results = plm.search_engineering_items("LandingGear")
created = plm.create_engineering_item("Strut Bracket", description="7075-T6")
plm.set_maturity_state(created["member"][0]["id"], "RELEASED")
```

---

## Running Tests

### Offline Unit Tests (No 3DEXPERIENCE Client Required)

```bash
python -m unittest discover -s tests/unit -v
# or with pytest:
pytest tests/unit -v
```

### Live 3DEXPERIENCE Integration Tests

Launch **3DEXPERIENCE** first. Test entities (`3DPart`, `3DShape`, `Drawing`) are verified or created automatically in any UI language, and your open documents are left untouched:

```bash
pytest -v --cov-report term-missing --cov=pycatia3dx
```
