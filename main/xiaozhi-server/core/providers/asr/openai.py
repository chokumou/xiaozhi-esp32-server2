import time
import os
from config.logger import setup_logging
from typing import Optional, Tuple, List
from core.providers.asr.dto.dto import InterfaceType
from core.providers.asr.base import ASRProviderBase

import requests

TAG = __name__
logger = setup_logging()

class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        self.interface_type = InterfaceType.NON_STREAM
        self.api_key = config.get("api_key")
        # 环境变量回退：当配置里是 "${OPENAI_API_KEY}" 或为空时，使用环境变量
        if not self.api_key or (isinstance(self.api_key, str) and self.api_key.strip().startswith("${")):
            self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.api_url = config.get("base_url")
        self.model = config.get("model_name")        
        self.output_dir = config.get("output_dir")
        self.delete_audio_file = delete_audio_file

        os.makedirs(self.output_dir, exist_ok=True)

    async def speech_to_text(self, opus_data: List[bytes], session_id: str, audio_format="opus") -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        try:
            start_time = time.time()
            if audio_format == "pcm":
                pcm_data = opus_data
            else:
                pcm_data = self.decode_opus(opus_data)
            file_path = self.save_audio_to_file(pcm_data, session_id)

            logger.bind(tag=TAG).debug(
                f"音频文件保存耗时: {time.time() - start_time:.3f}s | 路径: {file_path}"
            )

            logger.bind(tag=TAG).info(f"file path: {file_path}")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }
            # Support project/organization headers for sk-proj keys
            project_id = os.getenv("OPENAI_PROJECT", "").strip()
            if project_id:
                headers["OpenAI-Project"] = project_id
            org_id = os.getenv("OPENAI_ORG", "").strip()
            if org_id:
                headers["OpenAI-Organization"] = org_id
            
            # 使用data参数传递模型名称（固定日本語）
            data = {
                "model": self.model,
                "language": "ja",
                "temperature": 0,
            }


            with open(file_path, "rb") as audio_file:  # 使用with语句确保文件关闭
                files = {
                    "file": audio_file
                }

                start_time = time.time()
                response = requests.post(
                    self.api_url,
                    files=files,
                    data=data,
                    headers=headers
                )
                elapsed = time.time() - start_time
                body_preview = response.text[:300] if isinstance(response.text, str) else str(response.text)[:300]
                logger.bind(tag=TAG).info(
                    f"ASR HTTP {response.status_code} in {elapsed:.3f}s | preview={body_preview}"
                )

            if response.status_code == 200:
                text = response.json().get("text", "")
                logger.bind(tag=TAG).info(f"ASR text='{text}'")
                return text, file_path
            else:
                raise Exception(f"API请求失败: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return "", None
        finally:
            # 文件清理逻辑
            if self.delete_audio_file and file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.bind(tag=TAG).debug(f"已删除临时音频文件: {file_path}")
                except Exception as e:
                    logger.bind(tag=TAG).error(f"文件删除失败: {file_path} | 错误: {e}")
        
