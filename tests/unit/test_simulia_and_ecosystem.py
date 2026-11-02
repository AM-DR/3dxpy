"""Offline unit tests for SIMULIA solvers, Abaqus scripting/INP/ODB, and 3DEXPERIENCE ecosystem tools."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pycatia3dx import (
    AbaqusInpDeck,
    AbaqusOdbReader,
    AbaqusRunner,
    CATBatchRunner,
    DelmiaController,
    DynamicCOMObject,
    DynamicCOMService,
    EnoviaClient,
    SimuliaSuite,
    ThreeDExperience,
    ThreeDXPlatformClient,
    UniversalClientController,
    Workbenches,
)
from pycatia3dx.ecosystem.brands import BioviaRunner, ExciteController, GeoviaRunner
from pycatia3dx.ecosystem.dynamic_com import snake_to_com_candidates
from pycatia3dx.ecosystem.platform_api import PlatformAPIError
from pycatia3dx.interfaces.application import Application
from pycatia3dx.interfaces.editor import Editor
from pycatia3dx.sim_plm.sim_plm_service import SIMPLMService
from pycatia3dx.simulia.abaqus import inspect_job_files, parse_dat_file, parse_msg_file, parse_sta_file
from pycatia3dx.simulia.client_bridge import SimuliaClientController
from pycatia3dx.simulia.solvers import (
    CSTController,
    FeSafeRunner,
    IsightRunner,
    PowerFlowRunner,
    SimpackRunner,
    ToscaRunner,
    Wave6Runner,
    XFlowRunner,
)
from pycatia3dx.sma_mpa_foundation.sim_execution_service import SimExecutionService


class FakeCOMDispatch:
    """Lightweight mock emulating a Windows IDispatch COM object."""

    _oleobj_ = True

    def __init__(self, name: str = "MockObj", **members):
        self.Name = name
        for k, v in members.items():
            setattr(self, k, v)


class TestAbaqusInpDeck(unittest.TestCase):
    def test_build_write_and_roundtrip_parse(self):
        deck = AbaqusInpDeck(heading="Bracket Static + Modal")
        deck.set_parameters({"THICK": 6.5, "LOAD_Y": -1200.0})
        deck.add_nodes({
            1: (0.0, 0.0, 0.0),
            2: (100.0, 0.0, 0.0),
            3: (100.0, 20.0, 0.0),
            4: (0.0, 20.0, 0.0),
        })
        deck.add_elements("CPS4R", {1: (1, 2, 3, 4)}, elset="ALL_ELS")
        # Also test 20-node hex element line wrapping (>16 integers per line)
        deck.add_elements("C3D20R", {2: tuple(range(1, 21))}, elset="HEX_ELS")
        deck.add_nset("FIXED", [1, 4])
        deck.add_nset("LOAD_NODES", [2, 3])
        deck.add_elset("DESIGN_DOMAIN", [1], generate=False)
        deck.add_isotropic_material(
            "AL7075",
            youngs_modulus=71700.0,
            poissons_ratio=0.33,
            density=2.81e-9,
            plastic_table=[(503.0, 0.0), (572.0, 0.05)],
            expansion_coeff=2.36e-5,
            conductivity=130.0,
            specific_heat=960e6,
        )
        deck.add_solid_section("ALL_ELS", "AL7075", thickness=6.5)
        deck.add_shell_section("HEX_ELS", "AL7075", thickness=2.0)
        deck.add_static_step(
            name="StaticTip",
            nlgeom=True,
            boundaries=[("FIXED", 1, 2, 0.0)],
            cloads=[("LOAD_NODES", 2, -1200.0)],
            dloads=[("ALL_ELS", "GRAV", 9810.0)],
        )
        deck.add_frequency_step(name="Modal10", num_eigenvalues=10, boundaries=[("FIXED", "ENCASTRE", None, None)])

        with tempfile.TemporaryDirectory() as tmp:
            inp_path = pathlib.Path(tmp) / "bracket.inp"
            deck.write(inp_path)
            parsed = AbaqusInpDeck.from_file(inp_path)

        self.assertEqual(parsed.count_nodes(), 4)
        self.assertEqual(len(parsed.find_blocks("MATERIAL", name="AL7075")), 1)
        self.assertEqual(len(parsed.find_blocks("STEP")), 2)
        self.assertEqual(len(parsed.find_blocks("PARAMETER")), 1)
        self.assertIn("THICK = 6.5", parsed.to_string())
        self.assertIn("NLGEOM=YES", parsed.to_string())


class TestAbaqusRunnerAndOdbBridge(unittest.TestCase):
    def test_job_command_construction(self):
        runner = AbaqusRunner(executable="abq2025")
        cmd = runner.build_job_command(
            "wing_spar",
            "wing_spar.inp",
            cpus=8,
            gpus=1,
            memory="16gb",
            mp_mode="mpi",
            double_precision="both",
            user_subroutine="umat.f",
            interactive=True,
            ask_delete=False,
        )
        self.assertEqual(cmd[0], "abq2025")
        self.assertIn("job=wing_spar", cmd)
        self.assertIn("input=wing_spar", cmd)
        self.assertIn("cpus=8", cmd)
        self.assertIn("gpus=1", cmd)
        self.assertIn("memory=16gb", cmd)
        self.assertIn("mp_mode=mpi", cmd)
        self.assertIn("double=both", cmd)
        self.assertIn("user=umat.f", cmd)
        self.assertIn("interactive", cmd)
        self.assertIn("ask_delete=OFF", cmd)

    def test_sta_msg_dat_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            (base / "demo.sta").write_text(
                "Abaqus/Standard 3DEXPERIENCE R2025x\n"
                " SUMMARY OF JOB INFORMATION:\n"
                " STEP  INC ATT SEVERE EQUIL TOTAL  TOTAL      STEP       INC OF\n"
                "   1     1  1U     0     3     3  0.000      0.000      0.1000\n"
                "   1     1  2      0     2     2  0.025D+00  0.025D+00  0.0250\n"
                "   1     2  1      0     1     1  1.000      1.000      0.9750\n"
                " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n",
                encoding="utf-8",
            )
            (base / "demo.msg").write_text(
                "***WARNING: SOLVER PIVOT NUMERICAL SINGULARITY\n"
                "            AT NODE 42 DOF 3\n",
                encoding="utf-8",
            )
            (base / "demo.dat").write_text("NORMAL OUTPUT\n", encoding="utf-8")

            status = inspect_job_files("demo", base)
            self.assertTrue(status.completed)
            self.assertFalse(status.failed)
            self.assertEqual(status.status_text, "COMPLETED")
            self.assertEqual(len(status.increments), 3)
            self.assertAlmostEqual(status.increments[1].step_time, 0.025)
            self.assertEqual(len(status.warnings), 1)
            self.assertIn("SINGULARITY", status.warnings[0])

            # Test failed STA parsing too
            (base / "failjob.sta").write_text(
                "   1     1  5U     0     9     9  0.000  0.000  1.000E-06\n"
                " THE ANALYSIS HAS NOT BEEN COMPLETED\n",
                encoding="utf-8",
            )
            (base / "failjob.dat").write_text(
                "***ERROR: TOO MANY ATTEMPTS MADE FOR THIS INCREMENT\n",
                encoding="utf-8",
            )
            fstatus = inspect_job_files("failjob", base)
            self.assertTrue(fstatus.failed)
            self.assertFalse(fstatus.completed)
            self.assertEqual(len(fstatus.errors), 1)
            self.assertEqual(parse_sta_file(base / "missing.sta").status_text, "UNKNOWN")
            self.assertEqual(parse_msg_file(base / "missing.msg"), ([], []))
            self.assertEqual(parse_dat_file(base / "missing.dat"), ([], []))

    def test_inline_python_and_odb_reader_with_mock_abaqus_launcher(self):
        """End-to-end test of execute_inline() and AbaqusOdbReader via a shim Abaqus launcher."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = pathlib.Path(tmp)
            # Create a mock odbAccess module + fake abaqus launcher script
            (tmp_dir / "odbAccess.py").write_text(
                "class _Val:\n"
                "    def __init__(self, elem, mises, data):\n"
                "        self.instance = type('I', (), {'name': 'PART-1-1'})()\n"
                "        self.nodeLabel = None\n"
                "        self.elementLabel = elem\n"
                "        self.integrationPoint = 1\n"
                "        self.mises = mises\n"
                "        self.magnitude = None\n"
                "        self.data = data\n"
                "        self.dataDouble = None\n"
                "class _Field:\n"
                "    componentLabels = ('S11', 'S22', 'S33', 'S12')\n"
                "    values = [_Val(1, 150.5, [150.0, 10.0, 0.0, 5.0]), _Val(2, 245.0, [240.0, 20.0, 0.0, 12.0])]\n"
                "    def getSubset(self, region=None):\n"
                "        return self\n"
                "class _Frame:\n"
                "    incrementNumber = 1\n"
                "    frameValue = 1.0\n"
                "    description = 'Increment 1: Step Time = 1.0'\n"
                "    fieldOutputs = {'S': _Field()}\n"
                "class _HistOut:\n"
                "    description = 'Strain energy'\n"
                "    data = [(0.0, 0.0), (0.5, 12.5), (1.0, 50.0)]\n"
                "class _HistReg:\n"
                "    historyOutputs = {'ALLSE': _HistOut()}\n"
                "class _Step:\n"
                "    number = 1\n"
                "    procedure = '*STATIC'\n"
                "    totalTime = 1.0\n"
                "    frames = [_Frame()]\n"
                "    historyRegions = {'Assembly ASSEMBLY': _HistReg()}\n"
                "class _Root:\n"
                "    instances = {'PART-1-1': type('Inst', (), {'nodeSets': {}, 'elementSets': {'SET-1': object()}})()}\n"
                "    nodeSets = {'FIXED': object()}\n"
                "    elementSets = {'ALL_ELS': object()}\n"
                "class _Odb:\n"
                "    steps = {'Step-1': _Step()}\n"
                "    rootAssembly = _Root()\n"
                "    def close(self):\n"
                "        pass\n"
                "def openOdb(path, readOnly=True):\n"
                "    return _Odb()\n",
                encoding="utf-8",
            )

            shim_py = tmp_dir / "fake_abaqus_driver.py"
            shim_py.write_text(
                "import os, runpy, sys\n"
                f"sys.path.insert(0, {repr(str(tmp_dir))})\n"
                "args = sys.argv[1:]\n"
                "if args[0] == 'python':\n"
                "    script = args[1]\n"
                "    sys.argv = [script] + args[2:]\n"
                "    runpy.run_path(script, run_name='__main__')\n"
                "elif args[0] in ('cae', 'viewer'):\n"
                "    for tok in args[1:]:\n"
                "        if tok.startswith('noGUI=') or tok.startswith('script='):\n"
                "            script = tok.split('=', 1)[1]\n"
                "            runpy.run_path(script, run_name='__main__')\n"
                "            break\n",
                encoding="utf-8",
            )

            if os.name == "nt":
                launcher = tmp_dir / "fake_abq.cmd"
                launcher.write_text(
                    f'@"{sys.executable}" "{shim_py}" %*\r\n',
                    encoding="utf-8",
                )
            else:
                launcher = tmp_dir / "fake_abq.sh"
                launcher.write_text(
                    f'#!/bin/sh\nexec "{sys.executable}" "{shim_py}" "$@"\n',
                    encoding="utf-8",
                )
                launcher.chmod(0o755)

            runner = AbaqusRunner(executable=launcher)

            def compute_volume_in_cae(payload):
                return {
                    "volume": payload["length"] * payload["width"] * payload["height"],
                    "material": payload["material"],
                }

            inline_res = runner.execute_inline(
                compute_volume_in_cae,
                {"length": 10.0, "width": 5.0, "height": 2.0, "material": "Ti6Al4V"},
                mode="cae",
            )
            self.assertTrue(inline_res.succeeded)
            self.assertEqual(inline_res.output_data, {"volume": 100.0, "material": "Ti6Al4V"})

            # Test OdbReader inspect, field output, history output, and CSV export!
            odb_reader = AbaqusOdbReader(tmp_dir / "mock.odb", runner=runner)
            meta = odb_reader.inspect()
            self.assertIn("Step-1", meta["steps"])
            self.assertEqual(meta["instances"], ["PART-1-1"])

            field = odb_reader.read_field_output("S", instance="PART-1-1", element_set="SET-1")
            self.assertAlmostEqual(field["max_mises"], 245.0)
            self.assertEqual(field["total_count"], 2)

            hist = odb_reader.read_history_output("ALLSE")
            self.assertEqual(len(hist["data"]), 3)
            self.assertAlmostEqual(hist["data"][-1]["value"], 50.0)

            csv_file = odb_reader.export_field_to_csv(tmp_dir / "stress.csv", "S")
            self.assertTrue(csv_file.exists())
            csv_text = csv_file.read_text(encoding="utf-8")
            self.assertIn("245.0", csv_text)
            self.assertIn("S11", csv_text)


class TestOtherSimuliaAndBrandSolvers(unittest.TestCase):
    def test_simulia_solvers_commands_and_decks(self):
        isight = IsightRunner("fipercmd")
        icmd = isight.build_run_command("opt.zmf", parameters={"thick": 3.2, "radius": 8.0})
        self.assertEqual(icmd[0], "fipercmd")
        self.assertIn("thick=3.2;radius=8.0", icmd[-1])

        tosca = ToscaRunner("tosca")
        par_txt = tosca.build_topology_par(
            fem_input="bracket.inp",
            design_elset="DESIGN_ELS",
            volume_fraction=0.25,
            max_iterations=40,
            frozen_nset="BOLT_HOLES",
        )
        self.assertIn("LE_VALUE = 0.25", par_txt)
        self.assertIn("ND_GROUP = BOLT_HOLES", par_txt)
        tcmd = tosca.build_command("topo.par", job_name="topo_run", solver="abaqus", cpus=6)
        self.assertIn("-scpus", tcmd)
        self.assertIn("6", tcmd)

        fesafe = FeSafeRunner("fe-safe")
        macro = fesafe.build_fatigue_macro(input_odb="a.odb", output_odb="a_life.odb")
        self.assertIn("analyse", macro)
        self.assertEqual(fesafe.executable, "fe-safe")

        simpack = SimpackRunner("simpack-slv", "simpack-script")
        self.assertEqual(simpack.solver_executable, "simpack-slv")
        self.assertEqual(simpack.script_executable, "simpack-script")

        cst = CSTController("cst_design_environment")
        self.assertEqual(cst.cli_executable, "cst_design_environment")

        self.assertEqual(PowerFlowRunner("exaqsub").executable, "exaqsub")
        self.assertEqual(XFlowRunner("xflow").executable, "xflow")
        self.assertEqual(Wave6Runner("wave6").executable, "wave6")
        self.assertEqual(BioviaRunner("cstool", "RunMatScript").pipeline_pilot_executable, "cstool")
        self.assertEqual(GeoviaRunner("surpac2").surpac_executable, "surpac2")
        self.assertEqual(ExciteController("deltagen").executable, "deltagen")

    def test_catia_batch_xml_and_catstart(self):
        batch = CATBatchRunner(catenv_name="CATIA.B428_Cloud", catenv_dir="C:/ProgramData/CATEnv")
        cs_cmd = batch.build_catstart_command("CNEXT.exe -batch")
        self.assertIn("-run", cs_cmd)
        self.assertIn("CATIA.B428_Cloud", cs_cmd)
        xml_str = batch.build_batch_xml(
            "BatchDXFIGESSTEP",
            {"TargetFormat": "STEP"},
            file_inputs=["part1.3dxml"],
            output_folder="out_step",
        )
        self.assertIn('name="BatchDXFIGESSTEP"', xml_str)
        self.assertIn('value="STEP"', xml_str)


class TestDynamicCOMAndServices(unittest.TestCase):
    def test_snake_case_to_dassault_com_candidates(self):
        self.assertIn("PLMCreate", snake_to_com_candidates("plm_create"))
        self.assertIn("SIMDynClashServices", snake_to_com_candidates("sim_dyn_clash_services"))
        self.assertIn("GetProductRootOccurrence", snake_to_com_candidates("get_product_root_occurrence"))
        self.assertIn("OLPDownloadService", snake_to_com_candidates("olp_download_service"))

    def test_dynamic_com_object_and_service_resolution(self):
        child = FakeCOMDispatch(name="AnalysisCase-1", Status="Ready")
        created_calls = []

        def _plm_create(sim_name, sim_type, ctx):
            created_calls.append((sim_name, sim_type, getattr(ctx, "Name", ctx)))
            return child

        raw_custom_svc = FakeCOMDispatch(name="CustomBioService", PLMCreate=_plm_create)
        raw_exec_svc = FakeCOMDispatch(
            name="SimExecutionSerivce",
            BasicExecuteAll=lambda ref: True,
        )
        raw_plm_svc = FakeCOMDispatch(name="SimPLMService")
        raw_init_svc = FakeCOMDispatch(
            name="SimInitializationService",
            SetSimulationInitialization=lambda app_n, typ_n: None,
        )

        def _get_session_service(svc_name: str):
            if svc_name == "SimExecutionSerivce":
                return raw_exec_svc
            if svc_name == "SimExecutionService":
                raise RuntimeError("COM server registered typo SimExecutionSerivce")
            if svc_name == "SimPLMService":
                return raw_plm_svc
            if svc_name == "SimInitializationService":
                return raw_init_svc
            if svc_name == "BIOVIAFutureService":
                return raw_custom_svc
            return None

        sys_svc_com = FakeCOMDispatch(
            name="SystemService",
            Evaluate=lambda code, lang, fn, params: (
                FakeCOMDispatch(name="NewSimRef"),
                FakeCOMDispatch(name="NewSimEditor"),
            ),
        )
        app_com = FakeCOMDispatch(
            name="3DEXPERIENCE",
            GetSessionService=_get_session_service,
            SystemService=sys_svc_com,
            StartWorkbench=lambda wb: None,
            GetWorkbenchId=lambda: Workbenches.PART_DESIGN,
        )
        app = Application(app_com)

        # 1. Case-insensitive lookup for SIMPLMService
        plm_svc = app.get_session_service("simplmservice")
        self.assertIsInstance(plm_svc, SIMPLMService)

        # 2. Automatic fallback from SimExecutionService -> SimExecutionSerivce
        exec_svc = app.get_session_service("SimExecutionService")
        self.assertIsInstance(exec_svc, SimExecutionService)

        # 3. DynamicCOMService fallback for brand-new unlisted 3DEXPERIENCE services
        bio_svc = app.get_session_service("BIOVIAFutureService")
        self.assertIsInstance(bio_svc, DynamicCOMService)
        ctx_wrapper = DynamicCOMObject(FakeCOMDispatch(name="MyMolecule"))
        res_obj = bio_svc.plm_create("LigandSim", "BioDocking", ctx_wrapper)
        self.assertIsInstance(res_obj, DynamicCOMObject)
        self.assertEqual(res_obj.name, "AnalysisCase-1")
        self.assertEqual(res_obj.status, "Ready")
        self.assertEqual(created_calls, [("LigandSim", "BioDocking", "MyMolecule")])

        # 4. Unknown service returning None still raises KeyError
        with self.assertRaises(KeyError):
            app.get_session_service("NonExistentServiceXYZ")

        # 5. Editor.get_service dynamic fallback
        edt_com = FakeCOMDispatch(
            name="Editor",
            GetService=lambda name: FakeCOMDispatch(name=name) if name == "GEOVIATerrainService" else None,
        )
        edt = Editor(edt_com)
        geo_svc = edt.get_service("GEOVIATerrainService")
        self.assertIsInstance(geo_svc, DynamicCOMService)

        # 6. SimuliaClientController create_simulation & execute_all_cases
        sim_ctrl = SimuliaClientController(application=app)
        sim_ref, sim_edt = sim_ctrl.create_simulation("BracketFEA", ctx_wrapper)
        self.assertEqual(sim_ref.name, "NewSimRef")
        self.assertEqual(sim_edt.name, "NewSimEditor")
        self.assertTrue(sim_ctrl.execute_all_cases(sim_ref))

        # 7. UniversalClientController
        uclient = UniversalClientController(application=app)
        self.assertEqual(uclient.current_workbench(), Workbenches.PART_DESIGN)

        # 8. DelmiaController OLP download/upload
        saved_dirs = []
        dl_raw = FakeCOMDispatch(
            name="OlpDownloadService",
            Resource=None,
            DownloadCallTasks=False,
            Translator="",
            SaveToFolder=lambda d: saved_dirs.append(d),
            Finalize=lambda: None,
        )
        up_events = []
        up_raw = FakeCOMDispatch(
            name="OlpUploadService",
            Resource=None,
            Translator="",
            ReplaceTasks=False,
            Parse=lambda: up_events.append("parse"),
            Upload=lambda: up_events.append("upload"),
            PostProcess=lambda: up_events.append("post"),
            Finalize=lambda: up_events.append("fin"),
        )
        delmia_app_com = FakeCOMDispatch(
            name="3DEXPERIENCE",
            GetSessionService=lambda s: dl_raw if "Download" in s else up_raw,
            SystemService=sys_svc_com,
        )
        delmia = DelmiaController(application=Application(delmia_app_com))
        with tempfile.TemporaryDirectory() as tmp:
            prog_file = pathlib.Path(tmp) / "main.ls"
            prog_file.write_text("/PROG MAIN\n/END\n", encoding="utf-8")
            out_d = delmia.download_robot_programs(
                FakeCOMDispatch("FANUC_R2000"),
                [FakeCOMDispatch("WeldTask1")],
                pathlib.Path(tmp) / "robot_out",
                translator="DELMIA Fanuc Translator",
            )
            self.assertTrue(out_d.exists())
            self.assertEqual(len(saved_dirs), 1)

            delmia.upload_robot_programs(
                FakeCOMDispatch("FANUC_R2000"),
                [prog_file],
                translator="DELMIA Fanuc Translator",
            )
            self.assertEqual(up_events, ["parse", "upload", "post", "fin"])


class TestThreeDXPlatformClient(unittest.TestCase):
    def test_passport_login_csrf_security_context_and_enovia_endpoints(self):
        recorded: list[tuple[str, str, dict[str, str], bytes | None]] = []

        def mock_transport(req: urllib.request.Request, timeout: float):
            headers = {k: v for k, v in req.header_items()}
            recorded.append((req.get_method(), req.full_url, headers, req.data))
            parsed = urllib.parse.urlparse(req.full_url)
            path = parsed.path

            if path.endswith("/login") and req.get_method() == "GET":
                return 200, {}, json.dumps({"lt": "LT-98765-CAS"}).encode("utf-8")
            if path.endswith("/login") and req.get_method() == "POST":
                return 200, {}, json.dumps({"authenticated": True}).encode("utf-8")
            if path.endswith("/CSRF"):
                return 200, {}, json.dumps({"csrf": {"name": "ENO_CSRF_TOKEN", "value": "CSRF-TOK-123"}}).encode("utf-8")
            if path.endswith("/pno/person"):
                return 200, {}, json.dumps({
                    "preferredcredentials": {
                        "role": {"name": "VPLMProjectLeader"},
                        "organization": {"name": "Company Name"},
                        "collabspace": {"name": "Common Space"},
                    },
                    "collabspaces": [
                        {
                            "name": "R&D Space",
                            "couples": [
                                {
                                    "role": {"name": "VPLMCreator"},
                                    "organization": {"name": "Company Name"},
                                }
                            ],
                        }
                    ],
                }).encode("utf-8")
            if path.endswith("/dseng:EngItem") and req.get_method() == "POST":
                return 200, {}, json.dumps({"member": [{"id": "ENG-001", "title": "TurbineBlade"}]}).encode("utf-8")
            if path.endswith("/maturity/changeState"):
                return 200, {}, json.dumps({"results": [{"id": "ENG-001", "maturityState": "RELEASED"}]}).encode("utf-8")
            if path.endswith("/search"):
                return 200, {}, json.dumps({"infos": {"nbtotal": 1}, "results": [{"id": "ENG-001"}]}).encode("utf-8")
            if path.endswith("/error"):
                return 403, {}, b'{"error": "Forbidden"}'
            return 200, {}, b"{}"

        client = EnoviaClient(
            space_url="https://tenant-space.3dexperience.3ds.com/enovia",
            passport_url="https://authn.3dexperience.3ds.com",
            search_url="https://tenant-search.3dexperience.3ds.com/federated",
            tenant="R1132100999",
            transport=mock_transport,
        )

        login_resp = client.login_3dpassport("engineer@company.com", "secret")
        self.assertTrue(login_resp["authenticated"])

        contexts = client.discover_security_contexts()
        self.assertEqual(contexts[0], "VPLMProjectLeader.Company Name.Common Space")
        self.assertIn("VPLMCreator.Company Name.R&D Space", contexts)
        self.assertEqual(client.security_context, "VPLMProjectLeader.Company Name.Common Space")

        created = client.create_engineering_item("TurbineBlade", description="Stage 1 HPT")
        self.assertEqual(created["member"][0]["id"], "ENG-001")

        # Verify SecurityContext and ENO_CSRF_TOKEN headers were sent on POST
        post_call = [c for c in recorded if c[1].find("dseng:EngItem") != -1 and c[0] == "POST"][0]
        header_map_lower = {k.lower(): v for k, v in post_call[2].items()}
        self.assertEqual(header_map_lower.get("eno_csrf_token"), "CSRF-TOK-123")
        self.assertEqual(header_map_lower.get("securitycontext"), "VPLMProjectLeader.Company Name.Common Space")

        mat = client.set_maturity_state("ENG-001", "RELEASED")
        self.assertEqual(mat["results"][0]["maturityState"], "RELEASED")

        fed = client.federated_search("TurbineBlade")
        self.assertEqual(fed["infos"]["nbtotal"], 1)

        with self.assertRaises(PlatformAPIError) as ctx:
            client.request("GET", "/error")
        self.assertEqual(ctx.exception.status_code, 403)


class TestUnifiedHub(unittest.TestCase):
    def test_hub_initialization_and_discovery(self):
        dx = ThreeDExperience()
        self.assertIsInstance(dx.simulia, SimuliaSuite)
        self.assertIsInstance(dx.batch, CATBatchRunner)
        plm = dx.platform("https://example-space.3dexperience.3ds.com/enovia")
        self.assertIsInstance(plm, ThreeDXPlatformClient)
        summary = dx.discover()
        self.assertIn("3dexperience_installations", summary)
        self.assertIn("abaqus_executable", summary)


if __name__ == "__main__":
    unittest.main()
