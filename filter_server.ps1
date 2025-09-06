# Usage: run this in the server repo directory after server.log exists
$patterns = @("※ここを見せて※","AUDIO_TRACE","UTT#","client_voice_stop","flush: cause","ASR text","TTS start","mbedtls_ssl_fetch_input")
Get-Content .\server.log -Wait -Tail 0 |
  Select-String -Pattern ($patterns -join "|") |
  Tee-Object server_filtered.log



