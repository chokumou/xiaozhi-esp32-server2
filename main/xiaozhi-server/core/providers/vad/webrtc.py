import time
import numpy as np
import opuslib_next
from config.logger import setup_logging
from core.providers.vad.base import VADProviderBase

TAG = __name__
logger = setup_logging()


class VADProvider(VADProviderBase):
    """
    轻量级WebRTC风格VAD实现：
    - 优先尝试webrtcvad库；如果不可用，则使用能量阈值退化判断
    - 兼容项目的连接状态字段（client_audio_buffer、client_voice_window等）
    - 输入为Opus帧，内部解码为PCM后检测
    """

    def __init__(self, config):
        # webrtcvad 可选导入
        try:
            import webrtcvad  # type: ignore
            self._vad = webrtcvad.Vad(int(config.get("aggressiveness", 2)))
        except Exception:
            self._vad = None

        self.decoder = opuslib_next.Decoder(16000, 1)

        # 双阈值退化参数（未安装webrtcvad时生效）
        # aggressiveness越大，threshold越低（更敏感）
        aggr = float(config.get("aggressiveness", 3))
        # 更敏感的能量阈值（平均绝对振幅）
        base = 120.0
        self.energy_threshold = base + max(0.0, 3 - aggr) * 60.0
        self.energy_threshold_low = self.energy_threshold * 0.6

        # 静默结束判定（時間しきい）
        self.silence_threshold_ms = int(config.get("min_silence_duration_ms", 300))
        # 静默结束判定（連続Falseフレーム数しきい）
        self.silence_false_frames = int(config.get("silence_false_frames", 10))

        # 至少多少帧判定为有声
        self.frame_window_threshold = 2

    def _is_voice_energy(self, pcm_chunk: bytes) -> bool:
        if not pcm_chunk:
            return False
        audio_int16 = np.frombuffer(pcm_chunk, dtype=np.int16)
        if audio_int16.size == 0:
            return False
        energy = np.mean(np.abs(audio_int16))
        return energy >= self.energy_threshold

    def is_vad(self, conn, opus_packet) -> bool:
        try:
            pcm_frame = self.decoder.decode(opus_packet, 960)
            conn.client_audio_buffer.extend(pcm_frame)

            client_have_voice = False
            frame_len_bytes = 512 * 2  # 512 samples per step

            while len(conn.client_audio_buffer) >= frame_len_bytes:
                chunk = conn.client_audio_buffer[:frame_len_bytes]
                conn.client_audio_buffer = conn.client_audio_buffer[frame_len_bytes:]

                if self._vad is not None:
                    # 使用webrtcvad（10/20/30ms帧）。512/16000≈32ms，近似可用
                    is_voice = False
                    try:
                        import webrtcvad  # type: ignore
                        # 需要16-bit mono little-endian PCM at 16kHz
                        is_voice = self._vad.is_speech(chunk, 16000)
                    except Exception:
                        is_voice = self._is_voice_energy(chunk)
                else:
                    is_voice = self._is_voice_energy(chunk)

                conn.last_is_voice = is_voice
                conn.client_voice_window.append(is_voice)
                client_have_voice = (
                    conn.client_voice_window.count(True) >= self.frame_window_threshold
                )

                # 連続無音カウントを更新
                if not hasattr(conn, "vad_consecutive_silence"):
                    conn.vad_consecutive_silence = 0
                if is_voice:
                    conn.vad_consecutive_silence = 0
                else:
                    conn.vad_consecutive_silence += 1

                # 有声->無音 への遷移タイミングを記録
                if conn.client_have_voice and not client_have_voice:
                    stop_duration = time.time() * 1000 - conn.last_activity_time
                    logger.bind(tag=TAG).info(
                        f"VAD voice->silence: silence_ms={stop_duration:.0f}, consecutive_false={conn.vad_consecutive_silence}"
                    )
                    if (
                        conn.vad_consecutive_silence >= self.silence_false_frames
                        or stop_duration >= self.silence_threshold_ms
                    ):
                        reason = (
                            "consecutive_false"
                            if conn.vad_consecutive_silence >= self.silence_false_frames
                            else "silence_ms"
                        )
                        logger.bind(tag=TAG).info(
                            f"VAD EoS: stop by {reason} (false={conn.vad_consecutive_silence}, silence_ms={stop_duration:.0f})"
                        )
                        try:
                            conn._stop_cause = f"vad:{reason}(false={conn.vad_consecutive_silence},ms={int(stop_duration)})"
                            logger.bind(tag=TAG).info(
                                f"[AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} client_voice_stop set by webrtc:vad reason={reason} false={conn.vad_consecutive_silence} last_activity_ms={int(stop_duration)}"
                            )
                        except Exception:
                            pass
                        conn.client_voice_stop = True
                if client_have_voice and not conn.client_have_voice:
                    logger.bind(tag=TAG).info(
                        f"VAD voice start: energy_threshold={self.energy_threshold:.1f}"
                    )
                if client_have_voice:
                    conn.client_have_voice = True
                    conn.last_activity_time = time.time() * 1000

            return client_have_voice
        except opuslib_next.OpusError as e:
            logger.bind(tag=TAG).info(f"解码错误: {e}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"VAD处理错误: {e}")


