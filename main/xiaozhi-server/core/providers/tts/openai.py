import requests
import os
from core.utils.util import check_model_key
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_key = config.get("api_key")
        self.api_url = config.get("api_url", "https://api.openai.com/v1/audio/speech")
        self.model = config.get("model", "tts-1")
        if config.get("private_voice"):
            self.voice = config.get("private_voice")
        else:
            self.voice = config.get("voice", "alloy")
        self.response_format = config.get("format", "wav")
        self.audio_file_type = config.get("format", "wav")

        # 处理空字符串的情况
        speed = config.get("speed", "1.0")
        self.speed = float(speed) if speed else 1.0

        self.output_file = config.get("output_dir", "tmp/")
        # Resolve API key from environment if placeholder is present
        if not self.api_key or str(self.api_key).strip() in ("${OPENAI_API_KEY}", "${ OPENAI_API_KEY }"):
            env_key = os.getenv("OPENAI_API_KEY", "")
            if env_key:
                self.api_key = env_key
                logger.bind(tag=TAG).info("TTS OpenAI API key loaded from environment variable OPENAI_API_KEY")

        model_key_msg = check_model_key("TTS", self.api_key)
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    async def text_to_speak(self, text, output_file):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Optional project/organization headers
        project_id = os.getenv("OPENAI_PROJECT")
        if project_id:
            headers["OpenAI-Project"] = project_id
        organization_id = os.getenv("OPENAI_ORG")
        if organization_id:
            headers["OpenAI-Organization"] = organization_id
        data = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "wav",
            "speed": self.speed,
        }
        response = requests.post(self.api_url, json=data, headers=headers)
        if response.status_code == 200:
            if output_file:
                with open(output_file, "wb") as audio_file:
                    audio_file.write(response.content)
            else:
                return response.content
        else:
            raise Exception(
                f"OpenAI TTS请求失败: {response.status_code} - {response.text}"
            )
