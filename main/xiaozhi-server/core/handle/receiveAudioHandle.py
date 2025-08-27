import time
import os
from config.runtime_flags import flags
import asyncio
import json
from core.handle.sendAudioHandle import send_stt_message
from core.handle.intentHandler import handle_user_intent
from core.utils.output_counter import check_device_output_limit
from core.handle.abortHandle import handleAbortMessage
from core.handle.sendAudioHandle import SentenceType
from core.utils.util import audio_to_data_stream

TAG = __name__


async def handleAudioMessage(conn, audio):
    # 当前片段是否有人说话
    # 原実装に沿ってVADで判定（但しVAD未就绪时先按listen状态处理，避免报错）
    if getattr(conn, "vad", None) is None:
        have_voice = conn.client_have_voice
    else:
        vad_result = conn.vad.is_vad(conn, audio)
        # Support both old boolean return and new dict return
        if isinstance(vad_result, dict):
            # respect dtx flag: tiny packets explicitly treated as non-voice
            if vad_result.get("dtx", False):
                have_voice = False
                # do not append to asr buffer; signal to caller that this is DTX
                audio = b""
            else:
                # unify key: use 'speech' as canonical
                have_voice = bool(vad_result.get("speech", False))
                # attach decoded pcm if provided
                if vad_result.get("pcm"):
                    audio = vad_result.get("pcm")
        else:
            have_voice = bool(vad_result)

    # デバッグ用途: 強制的に有声扱いし、一定フレームで自動停止
    # NOTE: Disabled by default to avoid forced early flush during normal testing.
    # To enable runtime forced-VAD for debugging, set VAD_FORCE_VOICE=1 and
    # re-enable the block below.
    # if os.getenv("VAD_FORCE_VOICE", "0") == "1" or flags.get("VAD_FORCE_VOICE", False):
    #     have_voice = True
    #     # カウンタを持たせて20フレーム程度で自動的にstopを立てる
    #     if not hasattr(conn, "_force_voice_frames"):
    #         conn._force_voice_frames = 0
    #     conn._force_voice_frames += 1
    #     if conn._force_voice_frames >= 20:
    #         conn.client_voice_stop = True
    #         try:
    #             conn._stop_cause = "debug:force_voice"
    #             conn.logger.bind(tag=TAG).info(
    #                 f"[AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} stop by debug force (frames={conn._force_voice_frames})"
    #             )
    #         except Exception:
    #             pass
    # DTX閾値: 非音声小パケットは完全無視（端末のDTX等）
    try:
        dtx_thr = int(os.getenv("DTX_THRESHOLD", "3"))
    except Exception:
        dtx_thr = 3
    if audio and len(audio) <= dtx_thr:
        # drop tiny/DTX packets: do not advance counters or trigger stop
        return

    # 如果设备刚刚被唤醒，短暂忽略VAD检测
    if have_voice and hasattr(conn, "just_woken_up") and conn.just_woken_up:
        have_voice = False
        # 设置一个短暂延迟后恢复VAD检测
        conn.asr_audio.clear()
        if not hasattr(conn, "vad_resume_task") or conn.vad_resume_task.done():
            conn.vad_resume_task = asyncio.create_task(resume_vad_detection(conn))
        return

    # 非DTX片が来たら起床処理：VAD状態リセット、wake_guardを設定
    now_ms = int(time.time() * 1000)
    if have_voice:
        # update last non-DTX receive time
        try:
            conn.last_non_dtx_time = now_ms
        except Exception:
            conn.last_non_dtx_time = now_ms
        # reset vad states on wake
        try:
            conn.reset_vad_states()
        except Exception:
            pass
        # wake guard: do not allow EoS for this many ms after wake (default 300ms)
        try:
            wake_guard = int((conn.config or {}).get("wake_guard_ms", os.getenv("WAKE_GUARD_MS", "300")))
        except Exception:
            wake_guard = 300
        conn.wake_until = now_ms + wake_guard

    if have_voice:
        if conn.client_is_speaking:
            # Disable barge-in: ignore incoming audio while server is speaking (debug only)
            conn.logger.bind(tag=TAG).debug("Barge-in ignored: speaking=True, incoming audio discarded")
            return
    # 设备长时间空闲检测，用于say goodbye
    await no_voice_close_connect(conn, have_voice)
    # 接收音频
    # Trace who triggers stop flag (log when set elsewhere)
    pre_stop = conn.client_voice_stop
    # Detailed trace before handing to ASR.receive_audio
    try:
        conn.logger.bind(tag=TAG).info(
            f"[AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} pre_recv client_have_voice={getattr(conn,'client_have_voice',False)} client_voice_stop={getattr(conn,'client_voice_stop',False)} have_voice_in={have_voice}"
        )
    except Exception:
        pass
    await conn.asr.receive_audio(conn, audio, have_voice)
    post_stop = conn.client_voice_stop
    if not pre_stop and post_stop:
        try:
            conn.logger.bind(tag=TAG).info(
                f"※ここを見せて※ [AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} client_voice_stop set by {getattr(conn,'_stop_cause', 'unknown')} ※ここを見せて※"
            )
        except Exception:
            pass
    # Post-receive trace
    try:
        conn.logger.bind(tag=TAG).info(
            f"[AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} post_recv client_have_voice={getattr(conn,'client_have_voice',False)} client_voice_stop={getattr(conn,'client_voice_stop',False)} rx_frames_since_listen={getattr(conn,'rx_frames_since_listen',0)} rx_bytes_since_listen={getattr(conn,'rx_bytes_since_listen',0)}"
        )
    except Exception:
        pass


async def resume_vad_detection(conn):
    # 等待2秒后恢复VAD检测
    await asyncio.sleep(1)
    conn.just_woken_up = False


async def startToChat(conn, text):
    # 检查输入是否是JSON格式（包含说话人信息）
    speaker_name = None
    actual_text = text

    try:
        # 尝试解析JSON格式的输入
        if text.strip().startswith('{') and text.strip().endswith('}'):
            data = json.loads(text)
            if 'speaker' in data and 'content' in data:
                speaker_name = data['speaker']
                actual_text = data['content']
                conn.logger.bind(tag=TAG).info(f"解析到说话人信息: {speaker_name}")

                # 直接使用JSON格式的文本，不解析
                actual_text = text
    except (json.JSONDecodeError, KeyError):
        # 如果解析失败，继续使用原始文本
        pass

    # 保存说话人信息到连接对象
    if speaker_name:
        conn.current_speaker = speaker_name
    else:
        conn.current_speaker = None

    if conn.need_bind:
        await check_bind_device(conn)
        return

    # 如果当日的输出字数大于限定的字数
    if conn.max_output_size > 0:
        if check_device_output_limit(
            conn.headers.get("device-id"), conn.max_output_size
        ):
            await max_out_size(conn)
            return
    if conn.client_is_speaking:
        await handleAbortMessage(conn)

    # 首先进行意图分析，使用实际文本内容
    intent_handled = await handle_user_intent(conn, actual_text)

    if intent_handled:
        # 如果意图已被处理，不再进行聊天
        return

    # 意图未被处理，继续常规聊天流程，使用实际文本内容
    await send_stt_message(conn, actual_text)
    conn.executor.submit(conn.chat, actual_text)


async def no_voice_close_connect(conn, have_voice):
    if have_voice:
        conn.last_activity_time = time.time() * 1000
        return
    # 只有在已经初始化过时间戳的情况下才进行超时检查
    if conn.last_activity_time > 0.0:
        no_voice_time = time.time() * 1000 - conn.last_activity_time
        close_connection_no_voice_time = int(
            conn.config.get("close_connection_no_voice_time", 120)
        )
        if (
            not conn.close_after_chat
            and no_voice_time > 1000 * close_connection_no_voice_time
        ):
            # 结束对话：不自动发送结束提示语（独自セリフを停止）
            conn.close_after_chat = True
            conn.client_abort = False
            await conn.close()
            return


async def max_out_size(conn):
    # 达到输出上限时，不自动发送提示语（独自セリフを停止）
    conn.close_after_chat = True


async def check_bind_device(conn):
    if conn.bind_code:
        # 确保bind_code是6位数字
        if len(conn.bind_code) != 6:
            conn.logger.bind(tag=TAG).error(f"无效的绑定码格式: {conn.bind_code}")
            text = "绑定码格式错误，请检查配置。"
            await send_stt_message(conn, text)
            return

        text = f"请登录控制面板，输入{conn.bind_code}，绑定设备。"
        await send_stt_message(conn, text)

        # 播放提示音
        music_path = "config/assets/bind_code.wav"
        conn.tts.tts_audio_queue.put((SentenceType.FIRST, [], text))
        play_audio_frames(conn, music_path)

        # 逐个播放数字
        for i in range(6):  # 确保只播放6位数字
            try:
                digit = conn.bind_code[i]
                num_path = f"config/assets/bind_code/{digit}.wav"
                play_audio_frames(conn, num_path)
            except Exception as e:
                conn.logger.bind(tag=TAG).error(f"播放数字音频失败: {e}")
                continue
        conn.tts.tts_audio_queue.put((SentenceType.LAST, [], None))
    else:
        text = f"没有找到该设备的版本信息，请正确配置 OTA地址，然后重新编译固件。"
        await send_stt_message(conn, text)
        music_path = "config/assets/bind_not_found.wav"
        conn.tts.tts_audio_queue.put((SentenceType.FIRST, [], text))
        play_audio_frames(conn, music_path)
        conn.tts.tts_audio_queue.put((SentenceType.LAST, [], None))


def play_audio_frames(conn, file_path):
    """播放音频文件并处理发送帧数据"""
    def handle_audio_frame(frame_data):
        conn.tts.tts_audio_queue.put((SentenceType.MIDDLE, frame_data, None))

    audio_to_data_stream(
        file_path,
        is_opus=True,
        callback=handle_audio_frame
    )
