import os
import wave
import uuid
import queue
import asyncio
import traceback
import threading
import opuslib_next
import json
import io
import time
import concurrent.futures
from abc import ABC, abstractmethod
from config.logger import setup_logging
from typing import Optional, Tuple, List, Dict, Any
from core.handle.receiveAudioHandle import startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.utils.util import remove_punctuation_and_length
from core.handle.receiveAudioHandle import handleAudioMessage

TAG = __name__
logger = setup_logging()


class ASRProviderBase(ABC):
    def __init__(self):
        pass

    # 打开音频通道
    async def open_audio_channels(self, conn):
        conn.asr_priority_thread = threading.Thread(
            target=self.asr_text_priority_thread, args=(conn,), daemon=True
        )
        conn.asr_priority_thread.start()

    # 有序处理ASR音频
    def asr_text_priority_thread(self, conn):
        while not conn.stop_event.is_set():
            try:
                message = conn.asr_audio_queue.get(timeout=1)
                future = asyncio.run_coroutine_threadsafe(
                    handleAudioMessage(conn, message),
                    conn.loop,
                )
                future.result()
            except queue.Empty:
                continue
            except Exception as e:
                logger.bind(tag=TAG).error(
                    f"处理ASR文本失败: {str(e)}, 类型: {type(e).__name__}, 堆栈: {traceback.format_exc()}"
                )
                continue

    # 接收音频
    async def receive_audio(self, conn, audio, *, audio_have_voice: bool):
        # FAILFAST: detect paths that deliver non-DTX audio without VAD
        # FAILFAST: only active in normal VAD mode. In RMS/NO_VAD modes we bypass.
        try:
            use_rms = os.getenv('NO_VAD', '0') == '1' or os.getenv('USE_RMS', '0') == '1'
            if not use_rms:
                if os.getenv("DEBUG_FAILFAST", "1") == "1":
                    if audio and len(audio) > 3 and not audio_have_voice and not getattr(conn, 'client_have_voice', False):
                        traceback.print_stack(limit=5)
                        raise RuntimeError("[FAILFAST] non-DTX arrived with have_voice=False → VAD not called on this path")
        except Exception:
            # Re-raise so devs can see the failure; do not swallow
            raise
        # BYPASS detection: if non-DTX audio keeps arriving but have_voice is False,
        # that indicates VAD was not called on the path delivering audio.
        audio_have_voice_flag = bool(audio_have_voice)
        # ASR ingress visibility: only log when we actually have voice
        try:
            if audio_have_voice_flag:
                est_pcm = 0
                if conn.audio_format == "pcm":
                    est_pcm = sum(len(x) for x in conn.asr_audio) if getattr(conn, 'asr_audio', None) is not None else 0
                else:
                    est_pcm = len(getattr(conn, 'asr_audio', [])) * 1920
                logger.bind(tag=TAG).info(f"[ASR_IN] hv=True pcm_bytes={est_pcm} sr=16000 ch=1 utt={getattr(conn,'utt_seq',0)}")
        except Exception:
            pass
        if audio and len(audio) > 3 and not audio_have_voice_flag and not getattr(conn, 'client_have_voice', False):
            conn._no_vad_streak = getattr(conn, '_no_vad_streak', 0) + 1
            if conn._no_vad_streak == 3:
                logger.bind(tag=TAG).error("[AUDIO_TRACE] BYPASS: non-DTX x3 but have_voice_in=False → VAD not called on this path")
                try:
                    hv = None
                    if getattr(conn, 'vad', None) is not None:
                        hv = conn.vad.is_vad(conn, audio)
                        logger.bind(tag=TAG).error(f"[AUDIO_TRACE] BYPASS_CHECK forced VAD → {hv}")
                    else:
                        logger.bind(tag=TAG).error("[AUDIO_TRACE] BYPASS_CHECK: conn.vad is None")
                except Exception as e:
                    logger.bind(tag=TAG).error(f"[AUDIO_TRACE] BYPASS_CHECK VAD error: {e}")
        else:
            conn._no_vad_streak = 0
        if conn.client_listen_mode == "auto" or conn.client_listen_mode == "realtime":
            have_voice = audio_have_voice
        else:
            have_voice = conn.client_have_voice
        
        if audio and len(audio) > 0:
            # If VAD returned a dict with dtx flag, ignore those chunks entirely
            if isinstance(audio, dict) and audio.get("dtx", False):
                # do not append or count DTX frames
                logger.bind(tag=TAG).info(
                    f"[AUDIO_TRACE] Ignored DTX chunk UTT#{getattr(conn,'utt_seq',0)}"
                )
            else:
                # append raw bytes (caller may pass pcm bytes)
                # If caller passed a dict with pcm field, extract it
                if isinstance(audio, dict) and audio.get("pcm"):
                    pcm_bytes = audio.get("pcm")
                else:
                    pcm_bytes = audio
                conn.asr_audio.append(pcm_bytes)
            # Per-chunk trace: size, have_voice flag, asr_audio length and estimated PCM
            try:
                if conn.audio_format == "pcm":
                    total_len_estimated_now = sum(len(x) for x in conn.asr_audio)
                else:
                    total_len_estimated_now = len(conn.asr_audio) * 1920
                logger.bind(tag=TAG).info(
                    f"[AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} recv_chunk size={len(audio)} have_voice={audio_have_voice} client_have_voice={getattr(conn,'client_have_voice',False)} asr_audio_frames={len(conn.asr_audio)} est_pcm={total_len_estimated_now}"
                )
            except Exception:
                pass
        # Do not trim audio during pre-voice; let VAD decide when enough voice has arrived
        if not have_voice and not conn.client_have_voice:
            return

        if conn.client_voice_stop:
            # Guard: ignore premature stop if accumulated audio is too small
            try:
                min_pcm_bytes = int(
                    (conn.config or {}).get("asr_min_pcm_bytes", os.getenv("ASR_MIN_PCM_BYTES", "12000"))
                )
            except Exception:
                min_pcm_bytes = 12000

            if conn.audio_format == "pcm":
                total_len_estimated = sum(len(x) for x in conn.asr_audio)
            else:
                # conn.asr_audio now holds PCM chunks only (we filter DTX upstream)
                total_len_estimated = sum(len(x) for x in conn.asr_audio)

            if total_len_estimated < min_pcm_bytes:
                logger.bind(tag=TAG).info(
                    f"※ここを見せて※ [AUDIO_TRACE] Early stop ignored: too small buffer ({total_len_estimated} < {min_pcm_bytes}), keep accumulating ※ここを見せて※"
                )
                # Simply drop the stop signal and continue accumulating
                conn.client_voice_stop = False
                return

            # Proceed with normal flush
            asr_audio_task = conn.asr_audio.copy()
            conn.asr_audio.clear()
            conn.reset_vad_states()

            if len(asr_audio_task) > 0:
                await self.handle_voice_stop(conn, asr_audio_task)
            conn.client_voice_stop = False

    # 处理语音停止
    async def handle_voice_stop(self, conn, asr_audio_task: List[bytes]):
        """并行处理ASR和声纹识别"""
        try:
            total_start_time = time.monotonic()
            
            # 准备音频数据
            if conn.audio_format == "pcm":
                pcm_data = asr_audio_task
            else:
                pcm_data = self.decode_opus(asr_audio_task)
            
            combined_pcm_data = b"".join(pcm_data)
            try:
                stop_cause = getattr(conn, "_stop_cause", None)
                logger.bind(tag=TAG).info(
                    f"※ここを見せて※ [AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} flush: cause={stop_cause}, frames={len(asr_audio_task)}, pcm_bytes={len(combined_pcm_data)} ※ここを見せて※"
                )
            except Exception:
                pass
            
            # 预先准备WAV数据
            wav_data = None
            # 使用连接的声纹识别提供者
            if conn.voiceprint_provider and combined_pcm_data:
                wav_data = self._pcm_to_wav(combined_pcm_data)
            
            
            # 定义ASR任务
            def run_asr():
                start_time = time.monotonic()
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # 送信ガード：極小/空の音声は送らない（config優先, envフォールバック）
                        try:
                            min_pcm_bytes = int(
                                (conn.config or {}).get("asr_min_pcm_bytes", os.getenv("ASR_MIN_PCM_BYTES", "12000"))
                            )
                        except Exception:
                            min_pcm_bytes = 12000
                        if conn.audio_format == "pcm":
                            total_len = sum(len(x) for x in asr_audio_task)
                        else:
                            # 粗い推定：Opus→PCMの目安（各フレームを960サンプル相当として計算）
                            total_len = len(asr_audio_task) * 1920  # 16-bit mono 960 samples
                        if total_len < min_pcm_bytes:
                            logger.bind(tag=TAG).info(
                                f"Skip ASR: too small audio ({total_len} bytes < {min_pcm_bytes})"
                            )
                            return ("", None)

                        result = loop.run_until_complete(
                            self.speech_to_text(asr_audio_task, conn.session_id, conn.audio_format)
                        )
                        end_time = time.monotonic()
                        logger.bind(tag=TAG).info(f"ASR耗时: {end_time - start_time:.3f}s")
                        return result
                    finally:
                        loop.close()
                except Exception as e:
                    end_time = time.monotonic()
                    logger.bind(tag=TAG).error(f"ASR失败: {e}")
                    return ("", None)
            
            # 定义声纹识别任务
            def run_voiceprint():
                if not wav_data:
                    return None
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # 使用连接的声纹识别提供者
                        result = loop.run_until_complete(
                            conn.voiceprint_provider.identify_speaker(wav_data, conn.session_id)
                        )
                        return result
                    finally:
                        loop.close()
                except Exception as e:
                    logger.bind(tag=TAG).error(f"声纹识别失败: {e}")
                    return None
            
            # 使用线程池执行器并行运行
            parallel_start_time = time.monotonic()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as thread_executor:
                asr_future = thread_executor.submit(run_asr)
                
                if conn.voiceprint_provider and wav_data:
                    voiceprint_future = thread_executor.submit(run_voiceprint)
                    
                    # 等待两个线程都完成
                    asr_result = asr_future.result(timeout=15)
                    voiceprint_result = voiceprint_future.result(timeout=15)
                    
                    results = {"asr": asr_result, "voiceprint": voiceprint_result}
                else:
                    asr_result = asr_future.result(timeout=15)
                    results = {"asr": asr_result, "voiceprint": None}
            
            
            # 处理结果
            raw_text, file_path = results.get("asr", ("", None))
            speaker_name = results.get("voiceprint", None)
            
            # 记录识别结果
            if raw_text:
                logger.bind(tag=TAG).info(f"识别文本: {raw_text}")
            if speaker_name:
                logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")
            
            # 性能监控
            total_time = time.monotonic() - total_start_time
            logger.bind(tag=TAG).info(f"总处理耗时: {total_time:.3f}s")
            
            # 检查文本长度
            text_len, _ = remove_punctuation_and_length(raw_text)
            self.stop_ws_connection()

            # 空文字のときは何も発話しない（独自自動セリフを停止）
            if text_len == 0:
                logger.bind(tag=TAG).info("ASR结果为空，无输出")
                return

            if text_len > 0:
                # 构建包含说话人信息的JSON字符串
                enhanced_text = self._build_enhanced_text(raw_text, speaker_name)
                
                # 使用自定义模块进行上报
                await startToChat(conn, enhanced_text)
                enqueue_asr_report(conn, enhanced_text, asr_audio_task)
                
        except Exception as e:
            logger.bind(tag=TAG).error(f"处理语音停止失败: {e}")
            import traceback
            logger.bind(tag=TAG).debug(f"异常详情: {traceback.format_exc()}")

    def _build_enhanced_text(self, text: str, speaker_name: Optional[str]) -> str:
        """构建包含说话人信息的文本"""
        if speaker_name and speaker_name.strip():
            return json.dumps({
                "speaker": speaker_name,
                "content": text
            }, ensure_ascii=False)
        else:
            return text

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """将PCM数据转换为WAV格式"""
        if len(pcm_data) == 0:
            logger.bind(tag=TAG).warning("PCM数据为空，无法转换WAV")
            return b""
        
        # 确保数据长度是偶数（16位音频）
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]
        
        # 创建WAV文件头
        wav_buffer = io.BytesIO()
        try:
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)      # 单声道
                wav_file.setsampwidth(2)      # 16位
                wav_file.setframerate(16000)  # 16kHz采样率
                wav_file.writeframes(pcm_data)
            
            wav_buffer.seek(0)
            wav_data = wav_buffer.read()
            
            return wav_data
        except Exception as e:
            logger.bind(tag=TAG).error(f"WAV转换失败: {e}")
            return b""

    def stop_ws_connection(self):
        pass

    def save_audio_to_file(self, pcm_data: List[bytes], session_id: str) -> str:
        """PCM数据保存为WAV文件"""
        module_name = __name__.split(".")[-1]
        file_name = f"asr_{module_name}_{session_id}_{uuid.uuid4()}.wav"
        file_path = os.path.join(self.output_dir, file_name)

        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 2 bytes = 16-bit
            wf.setframerate(16000)
            wf.writeframes(b"".join(pcm_data))

        return file_path

    @abstractmethod
    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, audio_format="opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本"""
        pass

    @staticmethod
    def decode_opus(opus_data: List[bytes]) -> List[bytes]:
        """将Opus音频数据解码为PCM数据"""
        try:
            decoder = opuslib_next.Decoder(16000, 1)
            pcm_data = []
            buffer_size = 960  # 每次处理960个采样点 (60ms at 16kHz)
            
            for i, opus_packet in enumerate(opus_data):
                try:
                    if not opus_packet or len(opus_packet) == 0:
                        continue
                    
                    pcm_frame = decoder.decode(opus_packet, buffer_size)
                    if pcm_frame and len(pcm_frame) > 0:
                        pcm_data.append(pcm_frame)
                        
                except opuslib_next.OpusError as e:
                    logger.bind(tag=TAG).warning(f"Opus解码错误，跳过数据包 {i}: {e}")
                except Exception as e:
                    logger.bind(tag=TAG).error(f"音频处理错误，数据包 {i}: {e}")
            
            return pcm_data
            
        except Exception as e:
            logger.bind(tag=TAG).error(f"音频解码过程发生错误: {e}")
            return []
