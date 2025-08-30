import time
import os
import numpy as np
import opuslib_next
import audioop
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
            # allow env override for quick testing: VAD_AGGR=1 or 0
            try:
                aggr = int(os.getenv("VAD_AGGR", config.get("aggressiveness", 2)))
            except Exception:
                aggr = int(config.get("aggressiveness", 2))
            self._vad = webrtcvad.Vad(aggr)
        except Exception:
            self._vad = None

        # Decoder: prefer explicit nominal output rate/channels
        self._decoder_sr = 16000
        self._decoder_ch = 1
        self.decoder = opuslib_next.Decoder(self._decoder_sr, self._decoder_ch)

        # Robust preprocessing helper: downmix and resample based on declared
        # input sample-rate/channels. Keeps ratecv state per input configuration.
        class VADPreproc:
            def __init__(self, vad_sr=16000, frame_ms=20, downmix_mode="left"):
                self.vad_sr = vad_sr
                self.frame_samples = vad_sr * frame_ms // 1000
                self._rcv_state = None
                self._buf = bytearray()
                self.downmix_mode = downmix_mode
                self._last_in_sr = None
                self._last_in_ch = None

            def _downmix(self, pcm_s16le: bytes, in_ch: int) -> bytes:
                if in_ch == 1:
                    return pcm_s16le
                try:
                    if self.downmix_mode == "left":
                        return audioop.tomono(pcm_s16le, 2, 1.0, 0.0)
                    elif self.downmix_mode == "maxabs":
                        L = audioop.tomono(pcm_s16le, 2, 1.0, 0.0)
                        R = audioop.tomono(pcm_s16le, 2, 0.0, 1.0)
                        return audioop.add(L, R, -1)
                    else:
                        return audioop.tomono(pcm_s16le, 2, 0.5, 0.5)
                except Exception:
                    return pcm_s16le

            def push(self, pcm_frame: bytes, in_sr: int, in_ch: int):
                if self._last_in_sr != in_sr or self._last_in_ch != in_ch:
                    # reset rate conversion state when input params change
                    self._rcv_state = None
                    self._last_in_sr = in_sr
                    self._last_in_ch = in_ch

                mono = self._downmix(pcm_frame, in_ch)

                if in_sr != self.vad_sr:
                    try:
                        mono16k, self._rcv_state = audioop.ratecv(
                            mono, 2, 1, in_sr, self.vad_sr, self._rcv_state
                        )
                    except Exception:
                        mono16k = mono
                        self._rcv_state = None
                else:
                    mono16k = mono

                try:
                    self._buf.extend(mono16k)
                except Exception:
                    pass

            def pop_frames(self, frame_bytes: int):
                out = []
                while len(self._buf) >= frame_bytes:
                    out.append(bytes(self._buf[:frame_bytes]))
                    del self._buf[:frame_bytes]
                return out

        self._preproc = VADPreproc(vad_sr=self._VAD_SR, frame_ms=self._VAD_FRAME_MS, downmix_mode=config.get("downmix_mode", "left"))

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

        # DTX(1-byte) silence handling: require a short prior voiced-run
        # before counting consecutive 1-byte frames as silence. This avoids
        # false-positive DTX sequences when no real voice was established.
        self.dtx_require_voice_frames = int(config.get("dtx_require_voice_frames", 2))

        # VAD framing constants (WebRTC supports 8/16/32k and 10/20/30ms frames)
        self._VAD_SR = 16000
        self._VAD_FRAME_MS = 20
        self._VAD_FRAME_SAMPLES = self._VAD_SR * self._VAD_FRAME_MS // 1000
        self._VAD_FRAME_BYTES = self._VAD_FRAME_SAMPLES * 2

        # startup info for debugging
        try:
            logger.bind(tag=TAG).info(
                f"VAD init: VAD_SR={self._VAD_SR} FRAME_MS={self._VAD_FRAME_MS} FRAME_BYTES={self._VAD_FRAME_BYTES} aggressiveness={config.get('aggressiveness', None)}"
            )
        except Exception:
            pass

    def _is_voice_energy(self, pcm_chunk: bytes) -> bool:
        if not pcm_chunk:
            return False
        audio_int16 = np.frombuffer(pcm_chunk, dtype=np.int16)
        if audio_int16.size == 0:
            return False
        energy = np.mean(np.abs(audio_int16))
        return energy >= self.energy_threshold

    def is_vad(self, conn, opus_packet) -> dict:
        """Return dict: {dtx: bool, speech: bool, silence_advance: bool, pcm: bytes}
        Backwards-compatible: if older caller expects bool, the caller should
        treat a dict as truthy when 'speech' is True.
        """
        try:
            # Visibility: log entry to show VAD is invoked for this packet
            try:
                logger.bind(tag=TAG).info(f"[AUDIO_TRACE] VAD_ENTER pkt_bytes={len(opus_packet)}")
            except Exception:
                pass
            # DTX tiny packet check at the Opus packet boundary
            if not opus_packet or len(opus_packet) <= 12:
                return {"dtx": True, "speech": False, "silence_advance": True, "pcm": b""}

            pcm_frame = self.decoder.decode(opus_packet, 960)
            # log decoded length for debugging
            try:
                decoded_len = len(pcm_frame) if pcm_frame else 0
                logger.bind(tag=TAG).info(f"[AUDIO_TRACE] VAD_DECODED pcm_bytes={decoded_len}")
            except Exception:
                pass
            # keep original decoded PCM for ASR path
            conn.client_audio_buffer.extend(pcm_frame)

            # Prepare VAD-specific 16kHz stash. Decoder may output at different
            # rates depending on upstream; to be robust, if decoded frame
            # appears large (>2000 bytes) assume 24kHz and resample to 16kHz.
            try:
                # Robust preprocessing: use declared decoder nominal sr/ch
                try:
                    in_sr = getattr(self, '_decoder_sr', 16000) or 16000
                    in_ch = getattr(self, '_decoder_ch', 1) or 1
                except Exception:
                    in_sr = 16000
                    in_ch = 1

                try:
                    # feed decoded PCM into preproc which handles downmix/resample
                    self._preproc.push(pcm_frame, in_sr=in_sr, in_ch=in_ch)
                    # Use the configured VAD frame size (self._VAD_FRAME_BYTES)
                    frames = self._preproc.pop_frames(self._VAD_FRAME_BYTES)
                except Exception:
                    # fallback: treat pcm_frame as single frame if anything fails
                    frames = [pcm_frame]
            except Exception:
                pcm_16k = pcm_frame

            # Frame-level tracing for debugging
            try:
                if not hasattr(self, "_frame_idx"):
                    self._frame_idx = 0
            except Exception:
                self._frame_idx = 0

            client_have_voice = False
            # VAD uses configured frame size (16kHz, 20ms)
            if not hasattr(self, "_vad_stash"):
                self._vad_stash = b""
            # append newly produced frames to local stash
            try:
                for f in frames:
                    self._vad_stash += f
            except Exception:
                # fallback: ensure at least original pcm_frame is present
                try:
                    self._vad_stash += pcm_frame
                except Exception:
                    pass

            FRAME_BYTES = self._VAD_FRAME_BYTES

            while len(self._vad_stash) >= FRAME_BYTES:
                frame = self._vad_stash[:FRAME_BYTES]
                self._vad_stash = self._vad_stash[FRAME_BYTES:]
                try:
                    logger.bind(tag=TAG).info(f"[AUDIO_TRACE] VAD_FRAME bytes={len(frame)}")
                except Exception:
                    pass

                # type/len check
                try:
                    if not isinstance(frame, (bytes, bytearray)) or len(frame) != FRAME_BYTES:
                        logger.bind(tag=TAG).info(
                            f"[VAD_DBG] bad_frame UTT#{getattr(conn,'utt_seq',0)} type={type(frame)} len={len(frame)} expect={FRAME_BYTES}"
                        )
                        continue
                except Exception:
                    pass

                # RMS debug
                try:
                    import audioop as _audioop
                    rms = _audioop.rms(frame, 2)
                except Exception:
                    rms = 0
                try:
                    logger.bind(tag=TAG).info(f"[VAD_DBG] frame=20ms bytes={len(frame)} rms={rms}")
                except Exception:
                    pass

                # wake guard: if within wake period, do not allow EoS
                try:
                    now_ms = int(time.time() * 1000)
                    if getattr(conn, 'wake_until', 0) > now_ms:
                        # treat as active speech window: skip stop detection
                        pass
                except Exception:
                    pass

                # Ignore very small Opus-derived chunks (likely DTX 1-byte packets)
                try:
                    if len(frame) <= 2:
                        logger.bind(tag=TAG).info(
                            f"[AUDIO_TRACE] SKIP_SMALL_CHUNK UTT#{getattr(conn,'utt_seq',0)} chunk_bytes={len(frame)} (likely DTX)"
                        )
                        # treat as non-voice but only advance the consecutive-silence
                        # counter if we previously observed enough voiced frames.
                        if not hasattr(conn, 'vad_consecutive_silence'):
                            conn.vad_consecutive_silence = 0
                        # Ensure we have a recent voiced-run counter
                        if not hasattr(conn, 'vad_recent_voice_frames'):
                            conn.vad_recent_voice_frames = 0
                        if conn.vad_recent_voice_frames >= self.dtx_require_voice_frames:
                            conn.vad_consecutive_silence += 1
                        # continue to next available chunk
                        continue
                except Exception:
                    pass

                if self._vad is not None:
                    # 使用webrtcvad（10/20/30msフレーム）
                    is_voice = False
                    try:
                        import webrtcvad  # type: ignore
                        # wake-aware RMS fallback
                        try:
                            import audioop as _audioop
                            rms_val = _audioop.rms(frame, 2)
                        except Exception:
                            rms_val = 0
                        now_ms = int(time.time() * 1000)
                        wake_until = getattr(conn, 'wake_until', 0)
                        if wake_until > now_ms and rms_val > 150:
                            is_voice = True
                        else:
                            # call actual vad
                            is_voice = self._vad.is_speech(frame, self._VAD_SR)
                    except Exception:
                        is_voice = self._is_voice_energy(frame)
                else:
                    # fallback energy-based
                    is_voice = self._is_voice_energy(frame)

                conn.last_is_voice = is_voice
                conn.client_voice_window.append(is_voice)
                client_have_voice = (
                    conn.client_voice_window.count(True) >= self.frame_window_threshold
                )

                # Detailed per-frame trace (only when AUDIO_TRACE is enabled)
                try:
                    # compute simple RMS to help debug why VAD may be silent
                    try:
                        import audioop as _audioop
                        rms_val = _audioop.rms(frame, 2)
                    except Exception:
                        rms_val = 0

                    # dynamic RMS gate: lower threshold within wake guard
                    try:
                        now_ms = int(time.time() * 1000)
                        wake_until = getattr(conn, 'wake_until', 0)
                        wake_gate = int(os.getenv('VAD_WAKE_RMS_GATE', '150'))
                        normal_gate = int(os.getenv('VAD_RMS_GATE', '200'))
                        threshold = wake_gate if wake_until > now_ms else normal_gate
                    except Exception:
                        threshold = 200

                    try:
                        if rms_val > threshold:
                            self._rms_cnt = getattr(self, "_rms_cnt", 0) + 1
                        else:
                            self._rms_cnt = 0
                    except Exception:
                        self._rms_cnt = 0

                    if getattr(self, "_rms_cnt", 0) >= 2:
                        logger.bind(tag=TAG).info(
                            f"[AUDIO_TRACE] VAD_DBG force speech by RMS UTT#{getattr(conn,'utt_seq',0)} rms={rms_val} thr={threshold}"
                        )
                        is_voice = True
                        self._rms_cnt = 0

                    logger.bind(tag=TAG).info(
                        f"[AUDIO_TRACE] VAD_FRAME UTT#{getattr(conn,'utt_seq',0)} frame_idx={self._frame_idx} frame_bytes={len(frame)} is_voice={is_voice} rms={rms_val} thr={threshold}"
                    )
                except Exception:
                    pass
                self._frame_idx += 1

                # 連続無音カウントを更新
                if not hasattr(conn, "vad_consecutive_silence"):
                    conn.vad_consecutive_silence = 0
                if is_voice:
                    conn.vad_consecutive_silence = 0
                    # record recent voiced frames so that subsequent DTX markers
                    # will be recognized as silence only after we actually had
                    # some voice.
                    try:
                        if not hasattr(conn, 'vad_recent_voice_frames'):
                            conn.vad_recent_voice_frames = 0
                        # cap the counter to avoid unbounded growth
                        conn.vad_recent_voice_frames = min(conn.vad_recent_voice_frames + 1, 1000)
                    except Exception:
                        pass
                else:
                    conn.vad_consecutive_silence += 1
                    # when non-voice frame appears, reset recent voiced-run
                    try:
                        conn.vad_recent_voice_frames = 0
                    except Exception:
                        pass

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

            return {"dtx": False, "speech": client_have_voice, "silence_advance": (not client_have_voice), "pcm": pcm_frame}
        except opuslib_next.OpusError as e:
            logger.bind(tag=TAG).info(f"解码错误: {e}")
        except Exception as e:
            logger.bind(tag=TAG).error(f"VAD处理错误: {e}")


