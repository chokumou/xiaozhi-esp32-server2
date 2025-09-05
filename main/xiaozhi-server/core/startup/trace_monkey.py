import inspect
import logging
import asyncio
from config.logger import setup_logging

logger = setup_logging()

def install_monkeypatches():
    try:
        from core.providers.vad.webrtc import VADProvider as WebrtcVAD
        from core.providers.asr.base import ASRProviderBase

        # patch is_vad (sync)
        orig_is_vad = WebrtcVAD.is_vad

        def traced_is_vad(self, conn, opus_packet):
            frm = inspect.stack()[1]
            try:
                logger.bind(tag=__name__).info(
                    f"[TRACE] VAD_ENTER from {frm.function} {frm.filename}:{frm.lineno} pkt={len(opus_packet)}"
                )
            except Exception:
                pass
            # mark ingress seen
            try:
                if hasattr(conn, '_ingress_seen'):
                    conn._ingress_seen.add('VAD_CALL')
            except Exception:
                pass
            return orig_is_vad(self, conn, opus_packet)

        WebrtcVAD.is_vad = traced_is_vad

        # patch receive_audio (async)
        orig_recv = ASRProviderBase.receive_audio

        async def traced_recv(self, conn, audio, have_voice):
            frm = inspect.stack()[1]
            try:
                logger.bind(tag=__name__).info(
                    f"[TRACE] ASR_RECV from {frm.function} {frm.filename}:{frm.lineno} size={len(audio) if audio else 0} have_voice={have_voice}"
                )
            except Exception:
                pass
            try:
                if hasattr(conn, '_ingress_seen'):
                    conn._ingress_seen.add('ASR_CALL')
            except Exception:
                pass
            return await orig_recv(self, conn, audio, have_voice)

        ASRProviderBase.receive_audio = traced_recv

    except Exception as e:
        try:
            logger.bind(tag=__name__).warning(f"trace_monkey install failed: {e}")
        except Exception:
            pass


try:
    install_monkeypatches()
except Exception:
    pass




