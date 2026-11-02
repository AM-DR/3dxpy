from __future__ import annotations

from typing import Type, Union

from pycatia3dx.dnb_fitting.fitting_service import FittingService
from pycatia3dx.dnb_igp_olp_use.calib_least_squares_service import CalibLeastSquaresService
from pycatia3dx.dnb_igp_olp_use.olp_download_service import OLPDownloadService
from pycatia3dx.dnb_igp_olp_use.olp_java_args import OLPJavaArgs
from pycatia3dx.dnb_igp_olp_use.olp_teach_helper import OLPTeachHelper
from pycatia3dx.dnb_igp_olp_use.olp_translator_helper import OLPTranslatorHelper
from pycatia3dx.dnb_igp_olp_use.olp_upload_service import OLPUploadService
from pycatia3dx.drafting.drawing_gen_service import DrawingGenService
from pycatia3dx.drafting.drawing_service import DrawingService
from pycatia3dx.ecosystem.dynamic_com import DynamicCOMService
from pycatia3dx.electrical.elec_import_finalizer_service import ElecImportFinalizerService
from pycatia3dx.fc_board.fcb_service import FCBService
from pycatia3dx.inertia.inertia_box_service import InertiaBoxService
from pycatia3dx.inertia.inertia_service import InertiaService
from pycatia3dx.interfaces.player_services import PlayerServices
from pycatia3dx.interfaces.service import Service
from pycatia3dx.interfaces.visu_services import VisuServices
from pycatia3dx.knowledge_interfaces.knowledge_services import KnowledgeServices
from pycatia3dx.material.matplm_service import MATPLMService
from pycatia3dx.measure.measurable_service import MeasurableService
from pycatia3dx.measure.measure_service import MeasureService
from pycatia3dx.opns_section.section_service import SectionService
from pycatia3dx.pcb_board.pcb_service import PCBService
from pycatia3dx.plm_access.plm_script_service import PLMScriptService
from pycatia3dx.plm_access.plm_search_service import PLMSearchService
from pycatia3dx.plm_access.search_service import SearchService
from pycatia3dx.plm_application_context.plm_app_context import PLMAppContext
from pycatia3dx.plm_application_context.plm_refresh_service import PLMRefreshService
from pycatia3dx.plm_application_context.pn_o_service import PnOService
from pycatia3dx.plm_document.plm_document_services import PLMDocumentServices
from pycatia3dx.plm_interference.interference_services import InterferenceServices
from pycatia3dx.plm_session_builder.plm_new_service import PLMNewService
from pycatia3dx.plm_session_builder.plm_open_service import PLMOpenService
from pycatia3dx.plm_session_builder.plm_propagate_service import PLMPropagateService
from pycatia3dx.plm_simulation_engine.sim_dyn_clash_services import SimDynClashServices
from pycatia3dx.plm_validation.val_validation_service import VALValidationService
from pycatia3dx.sim_plm.sim_plm_service import SIMPLMService
from pycatia3dx.sim_plm.sim_simulation_service import SimSimulationService
from pycatia3dx.sim_rep.sim_compose_link_services import SimComposeLinkServices
from pycatia3dx.sim_rep.sim_link_services import SimLinkServices
from pycatia3dx.sim_rep.sim_publication_services import SimPublicationServices
from pycatia3dx.sim_rep.sim_rep_services import SimRepServices
from pycatia3dx.sma_mpa_foundation.sim_execution_service import SimExecutionService
from pycatia3dx.sma_mpa_foundation.sim_initialization_service import SimInitializationService
from pycatia3dx.space_reference_system.rfg_service import RfgService
from pycatia3dx.space_reference_system.srs_instantiate_service import SrsInstantiateService
from pycatia3dx.structure.str_service import StrService
from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService
from pycatia3dx.vpm_editor_context.product_session_service import ProductSessionService

ApplicationService = Union[
    CalibLeastSquaresService,
    DrawingGenService,
    DrawingService,
    DynamicCOMService,
    ElecImportFinalizerService,
    KnowledgeServices,
    MATPLMService,
    OLPDownloadService,
    OLPJavaArgs,
    OLPTeachHelper,
    OLPTranslatorHelper,
    OLPUploadService,
    PLMAppContext,
    PLMDocumentServices,
    PLMNewService,
    PLMOpenService,
    PLMPropagateService,
    PLMRefreshService,
    PLMScriptService,
    PLMSearchService,
    PnOService,
    ProductSessionService,
    SearchService,
    Service,
    SimExecutionService,
    SimInitializationService,
    SIMPLMService,
    SimSimulationService,
    VisuServices,
]

EditorService = Union[
    DrawingGenService,
    DrawingService,
    DynamicCOMService,
    ElecImportFinalizerService,
    FCBService,
    FittingService,
    InertiaBoxService,
    InertiaService,
    InterferenceServices,
    KnowledgeServices,
    MeasurableService,
    MeasureService,
    PCBService,
    PlayerServices,
    PLMDocumentServices,
    PLMProductService,
    RfgService,
    SectionService,
    Service,
    SimComposeLinkServices,
    SimDynClashServices,
    SimExecutionService,
    SimLinkServices,
    SimPublicationServices,
    SimRepServices,
    SimSimulationService,
    SrsInstantiateService,
    StrService,
    VALValidationService,
    VisuServices,
]

application_service_types: dict[str, dict[str, Type[Service]]] = {
    "CalibLeastSquaresService": {"type": CalibLeastSquaresService},
    "CATDrawingGenService": {"type": DrawingGenService},
    "CATDrawingService": {"type": DrawingService},
    "DrawingService": {"type": DrawingService},
    "ElecImportFinalizerService": {"type": ElecImportFinalizerService},
    "KnowledgeServices": {"type": KnowledgeServices},
    "MATPLMService": {"type": MATPLMService},
    "OlpDownloadService": {"type": OLPDownloadService},
    "OLPDownloadService": {"type": OLPDownloadService},
    "OlpJavaArgs": {"type": OLPJavaArgs},
    "OLPJavaArgs": {"type": OLPJavaArgs},
    "OlpTeachHelper": {"type": OLPTeachHelper},
    "OLPTeachHelper": {"type": OLPTeachHelper},
    "OlpTranslatorHelper": {"type": OLPTranslatorHelper},
    "OLPTranslatorHelper": {"type": OLPTranslatorHelper},
    "OlpUploadService": {"type": OLPUploadService},
    "OLPUploadService": {"type": OLPUploadService},
    "PLMAppContext": {"type": PLMAppContext},
    "PLMDocumentServices": {"type": PLMDocumentServices},
    "PLMNewService": {"type": PLMNewService},
    "PLMOpenService": {"type": PLMOpenService},
    "PLMPropagateService": {"type": PLMPropagateService},
    "PLMRefreshService": {"type": PLMRefreshService},
    "PLMScriptService": {"type": PLMScriptService},
    "PLMSearch": {"type": PLMSearchService},
    "PLMSearchService": {"type": PLMSearchService},
    "PnOService": {"type": PnOService},
    "ProductSessionService": {"type": ProductSessionService},
    "Search": {"type": SearchService},
    "SearchService": {"type": SearchService},
    "Service": {"type": Service},
    # Note: 3DEXPERIENCE's own COM registration uses "SimExecutionSerivce" in
    # several releases; register both spellings so either works cleanly.
    "SimExecutionService": {"type": SimExecutionService},
    "SimExecutionSerivce": {"type": SimExecutionService},
    "SimInitializationService": {"type": SimInitializationService},
    "SimPLMService": {"type": SIMPLMService},
    "SIMPLMService": {"type": SIMPLMService},
    "SimSimulationService": {"type": SimSimulationService},
    "VisuServices": {"type": VisuServices},
}

editor_service_types: dict[str, dict[str, Type[Service]]] = {
    "CATDrawingGenService": {"type": DrawingGenService},
    "CATDrawingService": {"type": DrawingService},
    "DrawingService": {"type": DrawingService},
    "ElecImportFinalizerService": {"type": ElecImportFinalizerService},
    "FCBService": {"type": FCBService},
    "FittingService": {"type": FittingService},
    "InertiaBoxService": {"type": InertiaBoxService},
    "InertiaService": {"type": InertiaService},
    "InterferenceServices": {"type": InterferenceServices},
    "KnowledgeServices": {"type": KnowledgeServices},
    "MeasurableService": {"type": MeasurableService},
    "MeasureService": {"type": MeasureService},
    "PCBService": {"type": PCBService},
    "PlayerServices": {"type": PlayerServices},
    "PLMDocumentServices": {"type": PLMDocumentServices},
    "PLMProductService": {"type": PLMProductService},
    "RfgService": {"type": RfgService},
    "SectionService": {"type": SectionService},
    "Service": {"type": Service},
    "SimComposeLinkServices": {"type": SimComposeLinkServices},
    "SIMDynClashServices": {"type": SimDynClashServices},
    "SimDynClashServices": {"type": SimDynClashServices},
    "SimExecutionService": {"type": SimExecutionService},
    "SimExecutionSerivce": {"type": SimExecutionService},
    "SimLinkServices": {"type": SimLinkServices},
    "SimPublicationServices": {"type": SimPublicationServices},
    "SimRepServices": {"type": SimRepServices},
    "SimSimulationService": {"type": SimSimulationService},
    "SrsInstantiateService": {"type": SrsInstantiateService},
    "StrService": {"type": StrService},
    "VALValidationService": {"type": VALValidationService},
    "VisuServices": {"type": VisuServices},
}


def resolve_service_entry(
    service_name: str,
    registry: dict[str, dict[str, Type[Service]]],
) -> tuple[str, Type[Service]] | None:
    """
    Look up ``service_name`` in ``registry`` (exact match first, then
    case-insensitive match), returning ``(canonical_com_name, wrapper_cls)``.
    """
    if service_name in registry:
        return service_name, registry[service_name]["type"]
    lower = service_name.lower()
    for key, entry in registry.items():
        if key.lower() == lower:
            return key, entry["type"]
    return None
