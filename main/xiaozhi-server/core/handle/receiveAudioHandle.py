import time
import os
from config.runtime_flags import flags
import asyncio
import json
import traceback
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
    # Ensure DTX tiny packets are dropped immediately (<=3 bytes)
    try:
        dtx_thr = int(os.getenv("DTX_THRESHOLD", "3"))
    except Exception:
        dtx_thr = 3
    if audio and len(audio) <= dtx_thr:
        try:
            conn.logger.bind(tag=TAG).info(f"[AUDIO_TRACE] DROP_DTX pkt={len(audio)}")
        except Exception:
            pass
        return

    # Always call VAD first, then ASR
    # Force VAD call here as a tripwire so we can detect unused ingress paths.
    if getattr(conn, "vad", None) is None:
        have_voice = conn.client_have_voice
    else:
        # mark ingress seq seen
        try:
            conn._ingress_seen.add('INGRESS_CALL')
        except Exception:
            pass
        # Tripwire: always call VAD here and log unconditionally
        try:
            # call VAD and capture structured result
            vad_result = conn.vad.is_vad(conn, audio)
            if isinstance(vad_result, dict):
                have_voice = bool(vad_result.get("speech", False))
            else:
                have_voice = bool(vad_result)
            # explicit tripwire log
            conn.logger.bind(tag=TAG).info(f"[AUDIO_TRACE] VAD_RESULT pkt={len(audio)} have_voice={have_voice}")
            # FAILFAST tripwire: if VAD somehow returned None/omitted, crash so we can trace caller
            if have_voice is None:
                traceback.print_stack(limit=5)
                raise RuntimeError("[FAILFAST] VAD not executed")
        except Exception as e:
            # If VAD fails, log and continue with conservative default
            try:
                conn.logger.bind(tag=TAG).error(f"[AUDIO_TRACE] VAD_CALL_ERROR: {e}")
            except Exception:
                pass
            have_voice = conn.client_have_voice

        # Voice-session tracking: only trigger end-of-speech after
        # we've observed a voiced run followed by silence for 1s.
        try:
            now_ms = int(time.time() * 1000)
            # entered voice
            if have_voice:
                if not getattr(conn, '_in_voice_active', False):
                    conn._in_voice_active = True
                # cancel any pending post-voice task
                try:
                    if hasattr(conn, '_voice_end_task') and conn._voice_end_task and not conn._voice_end_task.done():
                        conn._voice_end_task.cancel()
                except Exception:
                    pass
            else:
                # just exited a voiced run -> schedule 1s guard to flush
                if getattr(conn, '_in_voice_active', False):
                    conn._in_voice_active = False

                    async def _voice_end_wait(c):
                        try:
                            await asyncio.sleep(1.0)
                            if not getattr(c, 'client_have_voice', False) and not getattr(c, 'client_is_speaking', False):
                                try:
                                    c._stop_cause = 'post_voice_silence_1s'
                                    c.client_voice_stop = True
                                    c.logger.bind(tag=TAG).info(f"[AUDIO_TRACE] UTT#{getattr(c,'utt_seq',0)} voice ended -> forced stop after 1s")
                                except Exception:
                                    pass
                        except asyncio.CancelledError:
                            return
                        except Exception:
                            return

                    try:
                        conn._voice_end_task = asyncio.create_task(_voice_end_wait(conn))
                    except Exception:
                        pass
        except Exception:
            pass

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

    # Enforce VAD -> ASR path and pass have_voice as keyword to avoid positional mistakes
    try:
        # DTX (<=3B) is ignored here as a safety guard
        if audio and len(audio) <= 3:
            try:
                conn.logger.bind(tag=TAG).info(f"[AUDIO_TRACE] ENFORCE_DROP_DTX pkt={len(audio)}")
            except Exception:
                pass
            return

        vad_api = getattr(conn, 'vad_provider', None) or getattr(conn, 'vad', None)
        # Prefer RMS-based detection when VAD is unavailable or explicitly disabled
        use_rms = os.getenv("NO_VAD", "0") == "1" or os.getenv("USE_RMS", "0") == "1" or vad_api is None
        if use_rms:
            hv = False
            try:
                import audioop as _audioop
                import math
                # decode opus -> pcm if needed (avoid double-decode if audio is already pcm)
                pcm = None
                if getattr(conn, 'audio_format', 'opus') in ('pcm', 'pcm16', 's16'):
                    pcm = audio
                else:
                    if vad_api is not None and hasattr(vad_api, 'decoder'):
                        try:
                            pcm = vad_api.decoder.decode(audio, 960)
                        except Exception:
                            pcm = None
                    else:
                        try:
                            import opuslib_next

                            dec = opuslib_next.Decoder(16000, 1)
                            pcm = dec.decode(audio, 960)
                        except Exception:
                            pcm = None

                # DTX: if packet small we already returned earlier; extra guard
                if not pcm or len(pcm) == 0:
                    hv = False
                else:
                    # per-connection rms buffer for 20ms frames
                    frame_bytes = 2 * 16000 * 20 // 1000  # 640
                    if not hasattr(conn, '_rms_buf'):
                        conn._rms_buf = bytearray()
                    conn._rms_buf.extend(pcm)

                    # calibration: collect initial quiet samples for noise floor
                    now_ms = int(time.time() * 1000)
                    calib_window_ms = float(os.getenv('VAD_RMS_CALIB_MS', '800'))
                    if not hasattr(conn, '_rms_calib_start'):
                        conn._rms_calib_start = now_ms
                        conn._rms_calib_samples = []

                    # process available 20ms frames
                    while len(conn._rms_buf) >= frame_bytes:
                        chunk = bytes(conn._rms_buf[:frame_bytes])
                        del conn._rms_buf[:frame_bytes]
                        try:
                            rms = _audioop.rms(chunk, 2)
                        except Exception:
                            rms = 0
                        # during calibration window collect rms samples
                        if (now_ms - conn._rms_calib_start) <= calib_window_ms:
                            conn._rms_calib_samples.append(rms)
                            # postpone decision until at least one frame after calibration
                        # update running accumulator (leaky integrator)
                        acc = getattr(conn, '_rms_acc', 0.0)
                        tau = float(os.getenv('VAD_RMS_TAU_MS', '250'))
                        decay = math.exp(- (20.0 / max(1.0, tau)))
                        noise_floor = getattr(conn, '_rms_noise_floor', None)
                        if noise_floor is None and conn._rms_calib_samples:
                            # compute 20th percentile when calibration window completes
                            if (now_ms - conn._rms_calib_start) > calib_window_ms:
                                s = sorted(conn._rms_calib_samples)
                                idx = max(0, int(len(s) * 0.2) - 1)
                                conn._rms_noise_floor = s[idx] if s else 0
                                noise_floor = conn._rms_noise_floor
                        if noise_floor is None:
                            noise_floor = int(os.getenv('VAD_RMS_NOISE_FLOOR', '0'))
                        delta = max(0, rms - (noise_floor or 0))
                        acc = acc * decay + delta
                        conn._rms_acc = acc

                        # gate thresholds (ON/OFF) with hysteresis
                        try:
                            gate_on = int(os.getenv('VAD_RMS_GATE_ON', os.getenv('VAD_RMS_GATE', '200')))
                        except Exception:
                            gate_on = 200
                        try:
                            gate_off = os.getenv('VAD_RMS_GATE_OFF', None)
                            if gate_off is not None:
                                gate_off = int(gate_off)
                            else:
                                # OFF = ON -4dB ~= ON / 10^(4/20)
                                gate_off = int(gate_on / (10 ** (4.0 / 20.0)))
                        except Exception:
                            gate_off = int(gate_on * 0.63)

                        # convert acc comparison to use rms-like units by scaling
                        # Here we compare acc directly to gate thresholds scaled by frame length
                        # (acc is in linear amplitude units summed with decay); keep simple mapping
                        if acc >= gate_on:
                            hv = True
                        elif acc <= gate_off:
                            hv = False

                        # logging
                        try:
                            conn.logger.bind(tag=TAG).info(f"[AUDIO_TRACE] ENFORCE_RMS frame_rms={rms} acc={acc:.1f} noise={noise_floor} on={gate_on} off={gate_off} hv={hv}")
                        except Exception:
                            pass

                        # update last_non_dtx_time only on actual voiced detection
                        if hv:
                            try:
                                conn.last_non_dtx_time = int(time.time() * 1000)
                            except Exception:
                                pass

                        # --- 追加: RMSで決定した hv を connection のVADカウンタに反映 ---
                        try:
                            # ensure counters exist
                            if not hasattr(conn, 'vad_consecutive_silence'):
                                conn.vad_consecutive_silence = 0
                            if not hasattr(conn, 'vad_recent_voice_frames'):
                                conn.vad_recent_voice_frames = 0

                            if hv:
                                conn.vad_consecutive_silence = 0
                                conn.vad_recent_voice_frames = min(getattr(conn, 'vad_recent_voice_frames', 0) + 1, 1000)
                                conn.client_have_voice = True
                                # debounce last_voice_ms updates to avoid tiny-spike resets (default 100ms)
                                try:
                                    now_ms_local = int(time.time() * 1000)
                                    last_voice = getattr(conn, 'last_voice_ms', 0)
                                    debounce_ms = int(os.getenv('VAD_LAST_VOICE_DEBOUNCE_MS', '100'))
                                    if (now_ms_local - last_voice) > debounce_ms:
                                        conn.last_voice_ms = now_ms_local
                                except Exception:
                                    try:
                                        conn.last_voice_ms = int(time.time() * 1000)
                                    except Exception:
                                        pass
                                # update activity timestamp
                                try:
                                    conn.last_activity_time = int(time.time() * 1000)
                                except Exception:
                                    pass
                                # cancel pending voice-end task if any
                                try:
                                    if hasattr(conn, '_voice_end_task') and conn._voice_end_task and not conn._voice_end_task.done():
                                        conn._voice_end_task.cancel()
                                except Exception:
                                    pass
                            else:
                                # apply decay to rms accumulator even when no new frame is processed
                                try:
                                    tau = float(os.getenv('VAD_RMS_TAU_MS', '250'))
                                    decay = math.exp(- (20.0 / max(1.0, tau)))
                                    if hasattr(conn, '_rms_acc'):
                                        conn._rms_acc = getattr(conn, '_rms_acc', 0.0) * decay
                                except Exception:
                                    pass

                                conn.vad_consecutive_silence = getattr(conn, 'vad_consecutive_silence', 0) + 1
                                conn.vad_recent_voice_frames = 0

                                # schedule voice-end wait if we transitioned from voice
                                try:
                                    if getattr(conn, 'client_have_voice', False) and (not hasattr(conn, '_voice_end_task') or conn._voice_end_task.done()):
                                        conn._voice_end_task = asyncio.create_task(_voice_end_wait(conn))
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        # --- end追加 ---

                        # --- 追加: 常時ウォッチドッグで最終発話時刻を管理し、1s無音で強制EoS ---
                        try:
                            now_ms_watch = int(time.time() * 1000)
                            # update last_voice_ms on hv True
                            if hv:
                                conn.last_voice_ms = now_ms_watch
                                conn.silence_count = 0
                            else:
                                conn.silence_count = getattr(conn, 'silence_count', 0) + 1

                            # watchdog: if we thought we were in voice and it's been >=1s since last_voice_ms
                            if getattr(conn, 'client_have_voice', False):
                                last = getattr(conn, 'last_voice_ms', now_ms_watch)
                                if now_ms_watch - last >= 1000:
                                    # trigger EoS once
                                    if not getattr(conn, 'client_voice_stop', False):
                                        try:
                                            conn._stop_cause = 'watchdog_silence_1s'
                                        except Exception:
                                            pass
                                        conn.client_voice_stop = True
                                        conn.client_have_voice = False
                                        conn.silence_count = 0
                                        try:
                                            conn.logger.bind(tag=TAG).info(
                                                f"[AUDIO_TRACE] UTT#{getattr(conn,'utt_seq',0)} voice ended -> forced stop after 1s (watchdog)"
                                            )
                                        except Exception:
                                            pass

                            # EoS debug line
                            try:
                                last_voice_ago = now_ms_watch - getattr(conn, 'last_voice_ms', now_ms_watch)
                                conn.logger.bind(tag=TAG).info(
                                    f"[EoS_DBG] hv={hv} utter={getattr(conn,'client_have_voice',False)} acc={getattr(conn,'_rms_acc',0.0):.1f} sil={getattr(conn,'silence_count',0)} last_voice_ago={last_voice_ago:.0f}ms"
                                )
                            except Exception:
                                pass
                        except Exception:
                            pass
                        # --- endウォッチドッグ ---
                        # --- 追加: 最終ウォッチドッグ（DTX/tiny packet によるカウント中断を補償） ---
                        try:
                            now_ms_force = int(time.time() * 1000)
                            last_voice = getattr(conn, 'last_voice_ms', None)
                            force_thresh = int(os.getenv('VAD_FORCE_EOS_MS', '1000'))
                            # If we had recent voice in the past and now it's been >= force_thresh, force EoS
                            if last_voice is not None and not getattr(conn, 'client_voice_stop', False):
                                if now_ms_force - last_voice >= force_thresh:
                                    try:
                                        conn._stop_cause = 'force_watchdog_time'
                                    except Exception:
                                        pass
                                    conn.client_voice_stop = True
                                    conn.client_have_voice = False
                                    try:
                                        conn.logger.bind(tag=TAG).info(f"[AUDIO_TRACE] voice ended -> forced stop by final_watchdog (ms>{force_thresh}) UTT#{getattr(conn,'utt_seq',0)}")
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        # --- end最終ウォッチドッグ ---

            except Exception as e:
                try:
                    conn.logger.bind(tag=TAG).error(f"[AUDIO_TRACE] ENFORCE_RMS error: {e}")
                except Exception:
                    pass
                hv = conn.client_have_voice
        else:
            hv = vad_api.is_vad(conn, audio)
            try:
                conn.logger.bind(tag=TAG).info(f"[AUDIO_TRACE] ENFORCE_VAD pkt={len(audio)} hv={hv}")
            except Exception:
                pass

        # If in RMS/NO_VAD mode and this frame is considered silent (hv==False),
        # convert the packet to a DTX-like marker so ASR.receive_audio will ignore it
        # and we avoid passing non-DTX silent chunks that previously triggered FAILFAST.
        try:
            if use_rms and not hv:
                try:
                    pkt_len = len(audio) if isinstance(audio, (bytes, bytearray)) else 0
                except Exception:
                    pkt_len = 0
                try:
                    conn.logger.bind(tag=TAG).info(f"[AUDIO_TRACE] ENFORCE_RMS_DROP pkt={pkt_len} hv={hv}")
                except Exception:
                    pass
                # restore original behavior: replace silent non-DTX packet with DTX marker
                audio = {"dtx": True}
        except Exception:
            pass

        # Debug: snapshot before calling ASR
        try:
            try:
                pkt_len_dbg = len(audio) if isinstance(audio, (bytes, bytearray)) else (len(audio.get('pcm')) if isinstance(audio, dict) and audio.get('pcm') else 'dict')
            except Exception:
                pkt_len_dbg = 'NA'
            conn.logger.bind(tag=TAG).info(
                f"[AUDIO_DEBUG] pre_ASR_call pkt_len={pkt_len_dbg} pkt_type={'dtx' if isinstance(audio, dict) and audio.get('dtx') else 'pcm/opus'} hv={hv} client_have_voice={getattr(conn,'client_have_voice',False)} client_voice_stop={getattr(conn,'client_voice_stop',False)} vad_false_count={getattr(conn,'vad_consecutive_silence',None)} vad_recent_voice={getattr(conn,'vad_recent_voice_frames',None)} last_voice_ms={getattr(conn,'last_voice_ms',None)} rx_frames_since_listen={getattr(conn,'rx_frames_since_listen',None)}"
            )
        except Exception:
            pass

        # Call ASR and catch exceptions for clearer debug
        try:
            await conn.asr.receive_audio(conn, audio, audio_have_voice=hv)
        except Exception as e:
            try:
                conn.logger.bind(tag=TAG).error(f"[AUDIO_DEBUG] ASR.receive_audio exception: {e} audio_type={type(audio)} hv={hv}")
            except Exception:
                pass
            raise
    except Exception:
        # Re-raise so FAILFAST/stack traces surface in dev logs
        raise
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
