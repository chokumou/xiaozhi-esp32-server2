import time
import numpy as np
import torch
import opuslib_next
import audioop
from config.logger import setup_logging
from core.providers.vad.base import VADProviderBase

TAG = __name__
logger = setup_logging()


class VADProvider(VADProviderBase):
    def __init__(self, config):
        logger.bind(tag=TAG).info("SileroVAD", config)
        self.model, _ = torch.hub.load(
            repo_or_dir=config["model_dir"],
            source="local",
            model="silero_vad",
            force_reload=False,
        )

        self.decoder = opuslib_next.Decoder(16000, 1)

        # 处理空字符串的情况
        threshold = config.get("threshold", "0.5")
        threshold_low = config.get("threshold_low", "0.2")
        min_silence_duration_ms = config.get("min_silence_duration_ms", "1000")

        self.vad_threshold = float(threshold) if threshold else 0.5
        self.vad_threshold_low = float(threshold_low) if threshold_low else 0.2

        self.silence_threshold_ms = (
            int(min_silence_duration_ms) if min_silence_duration_ms else 1000
        )

        # 至少要多少帧才算有语音
        self.frame_window_threshold = 3
        # VAD framing constants for model compatibility
        self._VAD_SR = 16000
        self._VAD_FRAME_MS = 20
        self._VAD_FRAME_SAMPLES = self._VAD_SR * self._VAD_FRAME_MS // 1000
        self._VAD_FRAME_BYTES = self._VAD_FRAME_SAMPLES * 2
        try:
            logger.bind(tag=TAG).info(
                f"Silero VAD init: VAD_SR={self._VAD_SR} FRAME_MS={self._VAD_FRAME_MS} FRAME_BYTES={self._VAD_FRAME_BYTES} threshold={self.vad_threshold}"
            )
        except Exception:
            pass

    def is_vad(self, conn, opus_packet):
        """Return dict with dtx flag like webrtc.is_vad for compatibility.
        """
        try:
            # DTX tiny packet check
            if not opus_packet or len(opus_packet) <= 12:
                return {"dtx": True, "speech": False, "silence_advance": True, "pcm": b""}

            pcm_frame = self.decoder.decode(opus_packet, 960)
            conn.client_audio_buffer.extend(pcm_frame)  # 将新数据加入缓冲区

            # Ensure model receives 16kHz audio for Silero
            try:
                if len(pcm_frame) > 2000:
                    # likely 48kHz output -> resample down to 16k
                    state = getattr(self, "_rcv_state", None)
                    try:
                        pcm_16k, state = audioop.ratecv(pcm_frame, 2, 1, 48000, 16000, state)
                        self._rcv_state = state
                    except Exception:
                        pcm_16k = pcm_frame
                else:
                    pcm_16k = pcm_frame
            except Exception:
                pcm_16k = pcm_frame

            # Process in VAD frame units (16kHz, 20ms)
            client_have_voice = False
            if not hasattr(self, "_vad_stash"):
                self._vad_stash = b""
            # append resampled pcm_16k to local stash
            self._vad_stash += pcm_16k

            while len(self._vad_stash) >= self._VAD_FRAME_BYTES:
                chunk = self._vad_stash[: self._VAD_FRAME_BYTES]
                self._vad_stash = self._vad_stash[self._VAD_FRAME_BYTES :]

                # Ignore very small chunks (likely DTX 1-byte packets)
                try:
                    if len(chunk) <= 2:
                        logger.bind(tag=TAG).info(
                            f"[AUDIO_TRACE] SKIP_SMALL_CHUNK UTT#{getattr(conn,'utt_seq',0)} chunk_bytes={len(chunk)} (likely DTX)"
                        )
                        if not hasattr(conn, 'vad_consecutive_silence'):
                            conn.vad_consecutive_silence = 0
                        conn.vad_consecutive_silence += 1
                        continue
                except Exception:
                    pass

                # 转换为模型需要的张量格式 (16k)
                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                audio_tensor = torch.from_numpy(audio_float32)

                # 检测语音活动
                with torch.no_grad():
                    speech_prob = self.model(audio_tensor, 16000).item()

                # 双阈值判断
                if speech_prob >= self.vad_threshold:
                    is_voice = True
                elif speech_prob <= self.vad_threshold_low:
                    is_voice = False
                else:
                    is_voice = conn.last_is_voice

                # 声音没低于最低值则延续前一个状态，判断为有声音
                conn.last_is_voice = is_voice

                # 更新滑动窗口
                conn.client_voice_window.append(is_voice)
                client_have_voice = (conn.client_voice_window.count(True) >= self.frame_window_threshold)

                # 如果之前有声音，但本次没有声音，且与上次有声音的时间差已经超过了静默阈值，则认为已经说完一句话
                if conn.client_have_voice and not client_have_voice:
                    stop_duration = time.time() * 1000 - conn.last_activity_time
                    if stop_duration >= self.silence_threshold_ms:
                        try:
                            reason = f"silence_ms(ms={int(stop_duration)})"
                            conn._stop_cause = f"vad:{reason}"
                            logger.bind(tag=TAG).info(
                                f"[AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} client_voice_stop set by silero:vad reason={reason} last_activity_ms={int(stop_duration)}"
                            )
                        except Exception:
                            pass
                        conn.client_voice_stop = True
                if client_have_voice:
                    conn.client_have_voice = True
                    conn.last_activity_time = time.time() * 1000

                # Per-frame debug trace with RMS
                try:
                    try:
                        import audioop as _audioop
                        rms_val = _audioop.rms(chunk, 2)
                    except Exception:
                        rms_val = 0
                    logger.bind(tag=TAG).info(
                        f"[AUDIO_TRACE] VAD_FRAME UTT#{getattr(conn,'utt_seq',0)} frame_len={len(chunk)} speech_prob={speech_prob:.3f} is_voice={is_voice} rms={rms_val}"
                    )
                except Exception:
                    pass

            return client_have_voice
        except opuslib_next.OpusError as e:
            logger.bind(tag=TAG).info(f"解码错误: {e}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"Error processing audio packet: {e}")
