from typing import Dict, Any
from config.logger import setup_logging
from core.utils import tts, llm, intent, memory, vad, asr

TAG = __name__
logger = setup_logging()


def initialize_modules(
    logger,
    config: Dict[str, Any],
    init_vad=False,
    init_asr=False,
    init_llm=False,
    init_tts=False,
    init_memory=False,
    init_intent=False,
) -> Dict[str, Any]:
    """
    初始化所有模块组件

    Args:
        config: 配置字典

    Returns:
        Dict[str, Any]: 包含所有初始化后的模块的字典
    """
    modules = {}

    def _sel_conf(section: str, select_key: str) -> Dict[str, Any]:
        # 安全にセクション/選択キーの設定を取得（None対策）
        section_conf = config.get(section) or {}
        chosen = section_conf.get(select_key) or {}
        if not isinstance(chosen, dict):
            chosen = {}
        return chosen

    # 初始化TTS模块
    if init_tts:
        select_tts_module = config["selected_module"]["TTS"]
        modules["tts"] = initialize_tts(config)
        logger.bind(tag=TAG).info(f"初始化组件: tts成功 {select_tts_module}")

    # 初始化LLM模块
    if init_llm:
        select_llm_module = config["selected_module"]["LLM"]
        llm_conf = _sel_conf("LLM", select_llm_module)
        llm_type = llm_conf.get("type", select_llm_module)
        modules["llm"] = llm.create_instance(llm_type, llm_conf)
        logger.bind(tag=TAG).info(f"初始化组件: llm成功 {select_llm_module}")

    # 初始化Intent模块
    if init_intent:
        select_intent_module = config["selected_module"]["Intent"]
        intent_conf = _sel_conf("Intent", select_intent_module)
        intent_type = intent_conf.get("type", select_intent_module)
        modules["intent"] = intent.create_instance(intent_type, intent_conf)
        logger.bind(tag=TAG).info(f"初始化组件: intent成功 {select_intent_module}")

    # 初始化Memory模块
    if init_memory:
        select_memory_module = config["selected_module"]["Memory"]
        memory_conf = _sel_conf("Memory", select_memory_module)
        memory_type = memory_conf.get("type", select_memory_module)
        modules["memory"] = memory.create_instance(
            memory_type,
            memory_conf,
            config.get("summaryMemory", None),
        )
        logger.bind(tag=TAG).info(f"初始化组件: memory成功 {select_memory_module}")

    # 初始化VAD模块
    if init_vad:
        select_vad_module = config["selected_module"]["VAD"]
        vad_conf = _sel_conf("VAD", select_vad_module)
        vad_type = vad_conf.get("type", select_vad_module)
        modules["vad"] = vad.create_instance(vad_type, vad_conf)
        logger.bind(tag=TAG).info(f"初始化组件: vad成功 {select_vad_module}")

    # 初始化ASR模块
    if init_asr:
        try:
            select_asr_module = config["selected_module"]["ASR"]
            new_asr = initialize_asr(config)
            if new_asr is not None:
                modules["asr"] = new_asr
                logger.bind(tag=TAG).info(f"初始化组件: asr成功 {select_asr_module}")
            else:
                logger.bind(tag=TAG).warning("初始化组件: asr未就绪，稍后按需实例化")
        except Exception as e:
            logger.bind(tag=TAG).warning(f"初始化组件: asr失败，将延迟到连接阶段初始化: {str(e)}")
    return modules


def initialize_tts(config):
    select_tts_module = config["selected_module"]["TTS"]
    tts_conf = (config.get("TTS") or {}).get(select_tts_module) or {}
    if not isinstance(tts_conf, dict):
        tts_conf = {}
    tts_type = tts_conf.get("type", select_tts_module)
    new_tts = tts.create_instance(
        tts_type,
        tts_conf,
        str(config.get("delete_audio", True)).lower() in ("true", "1", "yes"),
    )
    return new_tts


def initialize_asr(config):
    select_asr_module = config["selected_module"]["ASR"]
    asr_conf = (config.get("ASR") or {}).get(select_asr_module) or {}
    if not isinstance(asr_conf, dict):
        asr_conf = {}
    asr_type = asr_conf.get("type", select_asr_module)
    new_asr = asr.create_instance(
        asr_type,
        asr_conf,
        str(config.get("delete_audio", True)).lower() in ("true", "1", "yes"),
    )
    logger.bind(tag=TAG).info("ASR模块初始化完成")
    return new_asr


def initialize_voiceprint(asr_instance, config):
    """初始化声纹识别功能"""
    voiceprint_config = config.get("voiceprint")
    if not voiceprint_config:
        return False  

    # 应用配置
    if not voiceprint_config.get("url") or not voiceprint_config.get("speakers"):
        logger.bind(tag=TAG).warning("声纹识别配置不完整")
        return False
        
    try:
        asr_instance.init_voiceprint(voiceprint_config)
        logger.bind(tag=TAG).info("ASR模块声纹识别功能已动态启用")
        logger.bind(tag=TAG).info(f"配置说话人数量: {len(voiceprint_config['speakers'])}")
        return True
    except Exception as e:
        logger.bind(tag=TAG).error(f"动态初始化声纹识别功能失败: {str(e)}")
        return False

