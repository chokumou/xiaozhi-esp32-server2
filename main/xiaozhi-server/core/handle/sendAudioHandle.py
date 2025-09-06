import json
import time
from core.providers.tts.dto.dto import SentenceType
from core.utils import textUtils
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


async def sendAudioMessage(conn, sentenceType, audios, text):
    logger.bind(tag=TAG).info(f"※ここだよ！ sendAudioMessage呼び出し sentenceType={sentenceType}, text='{text}', audios_type={type(audios)}, audios_len={len(audios) if hasattr(audios, '__len__') else 'N/A'}")
    
    if conn.tts.tts_audio_first_sentence:
        conn.logger.bind(tag=TAG).info(f"发送第一段语音: {text}")
        conn.tts.tts_audio_first_sentence = False
        await send_tts_message(conn, "start", None)

    if sentenceType == SentenceType.FIRST:
        await send_tts_message(conn, "sentence_start", text)

    await sendAudio(conn, audios)
    # 发送句子开始消息
    if sentenceType is not SentenceType.MIDDLE:
        conn.logger.bind(tag=TAG).info(f"发送音频消息: {sentenceType}, {text}")

    # 发送结束消息（如果是最后一个文本）
    if conn.llm_finish_task and sentenceType == SentenceType.LAST:
        await send_tts_message(conn, "stop", None)
        conn.client_is_speaking = False
        if conn.close_after_chat:
            await conn.close()


# 播放音频
async def sendAudio(conn, audios):
    if audios is None:
        logger.bind(tag=TAG).warning(f"※ここだよ！ 音声データなし: audios=None")
        return
    # 如果audios不是opus数组，则不需要进行遍历，可以直接发送;这里需要进行流控管理，防止发送过快引发客户端溢出
    if isinstance(audios, bytes):
        logger.bind(tag=TAG).info(f"※ここだよ！ WebSocket音声送信開始 bytes={len(audios)}")
        try:
            if hasattr(conn, 'websocket') and conn.websocket:
                await conn.websocket.send(audios)
                logger.bind(tag=TAG).info(f"※ここだよ！ WebSocket音声送信完了 bytes={len(audios)}")
            else:
                logger.bind(tag=TAG).error(f"※ここだよ！ WebSocket未接続: conn.websocket={getattr(conn, 'websocket', None)}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"※ここだよ！ WebSocket音声送信エラー: {e}")
    else:
        logger.bind(tag=TAG).warning(f"※ここだよ！ 予期しない音声データ形式: type={type(audios)}, len={len(audios) if hasattr(audios, '__len__') else 'N/A'}")


async def send_tts_message(conn, state, text=None):
    """发送 TTS 状态消息"""
    if text is None and state == "sentence_start":
        return
    message = {"type": "tts", "state": state, "session_id": conn.session_id}
    if text is not None:
        message["text"] = textUtils.check_emoji(text)

    # TTS播放结束
    if state == "stop":
        # 播放提示音
        tts_notify = conn.config.get("enable_stop_tts_notify", False)
        if tts_notify:
            stop_tts_notify_voice = conn.config.get(
                "stop_tts_notify_voice", "config/assets/tts_notify.mp3"
            )
            audios, _ = conn.tts.audio_to_opus_data(stop_tts_notify_voice)
            await sendAudio(conn, audios)
        # 清除服务端讲话状态
        conn.clearSpeakStatus()
        # 解除发话保護期間
        try:
            conn.speak_lock_until = 0.0
        except Exception:
            pass
    elif state == "start":
        # TTS開始から短時間は誤検知での打断を無視するためのロックを張る
        try:
            lock_ms = int(conn.config.get("tts_start_lock_ms", 1200))
        except Exception:
            lock_ms = 1200
        conn.speak_lock_until = time.time() + (lock_ms / 1000.0)
        conn.logger.bind(tag=TAG).info(
            f"TTS start: speaking guard enabled for {lock_ms}ms (until {conn.speak_lock_until:.3f})"
        )

    # 发送消息到客户端
    await conn.websocket.send(json.dumps(message))


async def send_stt_message(conn, text):
    """发送 STT 状态消息"""
    end_prompt_str = conn.config.get("end_prompt", {}).get("prompt")
    if end_prompt_str and end_prompt_str == text:
        await send_tts_message(conn, "start")
        return

    # 解析JSON格式，提取实际的用户说话内容
    display_text = text
    try:
        # 尝试解析JSON格式
        if text.strip().startswith('{') and text.strip().endswith('}'):
            parsed_data = json.loads(text)
            if isinstance(parsed_data, dict) and "content" in parsed_data:
                # 如果是包含说话人信息的JSON格式，只显示content部分
                display_text = parsed_data["content"]
                # 保存说话人信息到conn对象
                if "speaker" in parsed_data:
                    conn.current_speaker = parsed_data["speaker"]
    except (json.JSONDecodeError, TypeError):
        # 如果不是JSON格式，直接使用原始文本
        display_text = text
    stt_text = textUtils.get_string_no_punctuation_or_emoji(display_text)
    await conn.websocket.send(
        json.dumps({"type": "stt", "text": stt_text, "session_id": conn.session_id})
    )
    conn.client_is_speaking = True
    conn.logger.bind(tag=TAG).info("Set speaking=True by STT message")
    await send_tts_message(conn, "start")
