package xiaozhi.service;

import org.springframework.stereotype.Service;
import xiaozhi.dto.*;
import xiaozhi.entity.Firmware;
import xiaozhi.repository.FirmwareRepository;
import java.util.Optional;

@Service
public class OTAService {
    
    private final DeviceService deviceService;
    private final FirmwareRepository firmwareRepository;
    
    public OTAService(DeviceService deviceService, FirmwareRepository firmwareRepository) {
        this.deviceService = deviceService;
        this.firmwareRepository = firmwareRepository;
        
        // 初期ファームウェア情報を設定
        initializeFirmwareDatabase();
    }
    
    public OTACheckResponse checkUpdate(OTACheckRequest request) {
        String deviceType = request.getDeviceType() != null ? request.getDeviceType() : "ESP32";
        String currentVersion = request.getCurrentVersion();
        
        // デバイスの現在のバージョンを取得
        if (currentVersion == null && request.getDeviceId() != null) {
            currentVersion = deviceService.getCurrentFirmwareVersion(request.getDeviceId());
        }
        
        Optional<Firmware> latestFirmware = firmwareRepository.findByDeviceTypeAndIsLatestTrue(deviceType);
        
        if (latestFirmware.isEmpty()) {
            return new OTACheckResponse(false);
        }
        
        Firmware firmware = latestFirmware.get();
        
        // バージョン比較（簡易版）
        if (currentVersion == null || !currentVersion.equals(firmware.getVersion())) {
            return new OTACheckResponse(true, firmware.getVersion(), firmware.getDownloadUrl(), 
                                      firmware.getFileSize(), firmware.getChecksum());
        }
        
        return new OTACheckResponse(false);
    }
    
    public String getDownloadUrl(String version, String deviceType) {
        if (deviceType == null) {
            deviceType = "ESP32";
        }
        
        if (version == null) {
            // 最新バージョンのURLを返す
            Optional<Firmware> latest = firmwareRepository.findByDeviceTypeAndIsLatestTrue(deviceType);
            return latest.map(Firmware::getDownloadUrl).orElse("https://example.com/firmware/latest.bin");
        }
        
        // 指定バージョンのURLを返す
        Optional<Firmware> firmware = firmwareRepository.findByDeviceTypeAndVersion(deviceType, version);
        return firmware.map(Firmware::getDownloadUrl).orElse("https://example.com/firmware/" + version + ".bin");
    }
    
    private void initializeFirmwareDatabase() {
        // 既にデータがある場合は初期化しない
        if (firmwareRepository.count() > 0) {
            return;
        }
        
        // ESP32用の初期ファームウェア情報
        firmwareRepository.save(new Firmware("1.0.0", "ESP32", 
                "https://example.com/firmware/esp32_v1.0.0.bin", 1024000L, "abc123", false));
        firmwareRepository.save(new Firmware("1.1.0", "ESP32", 
                "https://example.com/firmware/esp32_v1.1.0.bin", 1048576L, "def456", true));
                
        // 他のデバイスタイプも追加可能
        firmwareRepository.save(new Firmware("1.0.0", "ESP32-S3", 
                "https://example.com/firmware/esp32s3_v1.0.0.bin", 2097152L, "ghi789", true));
    }
}
