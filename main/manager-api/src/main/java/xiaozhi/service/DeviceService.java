package xiaozhi.service;

import org.springframework.stereotype.Service;
import xiaozhi.dto.*;
import xiaozhi.entity.Device;
import xiaozhi.repository.DeviceRepository;
import java.time.LocalDateTime;
import java.util.UUID;
import java.util.Optional;

@Service
public class DeviceService {
    
    private final DeviceRepository deviceRepository;
    
    public DeviceService(DeviceRepository deviceRepository) {
        this.deviceRepository = deviceRepository;
    }
    
    public DeviceRegisterResponse registerDevice(DeviceRegisterRequest request) {
        // プロビジョニングキーの検証（簡易版）
        if (!"VALID_PROVISION_KEY".equals(request.getProvisionKey())) {
            throw new RuntimeException("Invalid provision key");
        }
        
        // 既存デバイスチェック
        Optional<Device> existingDevice = deviceRepository.findByMacAddress(request.getMacAddress());
        if (existingDevice.isPresent()) {
            // 既存デバイスの場合、トークンを再発行
            Device device = existingDevice.get();
            String newToken = generateToken();
            device.setAccessToken(newToken);
            device.setLastHeartbeat(LocalDateTime.now());
            device.setStatus("online");
            deviceRepository.save(device);
            return new DeviceRegisterResponse(device.getDeviceId(), newToken, "wss://nekota-server.com/ws");
        }
        
        // 新規デバイス登録
        String deviceId = "dev_" + UUID.randomUUID().toString().substring(0, 8);
        String accessToken = generateToken();
        
        Device device = new Device(deviceId, request.getMacAddress(), 
                                 request.getDeviceType(), request.getFirmwareVersion(), accessToken);
        deviceRepository.save(device);
        
        return new DeviceRegisterResponse(deviceId, accessToken, "wss://nekota-server.com/ws");
    }
    
    public void updateHeartbeat(String deviceId, String token) {
        // トークン検証
        if (!isValidToken(deviceId, token)) {
            throw new RuntimeException("Invalid token");
        }
        
        Optional<Device> deviceOpt = deviceRepository.findById(deviceId);
        if (deviceOpt.isEmpty()) {
            throw new RuntimeException("Device not found");
        }
        
        Device device = deviceOpt.get();
        device.setLastHeartbeat(LocalDateTime.now());
        device.setStatus("online");
        deviceRepository.save(device);
    }
    
    public String getDeviceStatus(String deviceId) {
        Optional<Device> deviceOpt = deviceRepository.findById(deviceId);
        if (deviceOpt.isEmpty()) {
            return "not_found";
        }
        
        Device device = deviceOpt.get();
        
        // 5分以上ハートビートがない場合はオフライン
        if (device.getLastHeartbeat().isBefore(LocalDateTime.now().minusMinutes(5))) {
            device.setStatus("offline");
            deviceRepository.save(device);
        }
        
        return device.getStatus();
    }
    
    public String getCurrentFirmwareVersion(String deviceId) {
        Optional<Device> deviceOpt = deviceRepository.findById(deviceId);
        return deviceOpt.map(Device::getFirmwareVersion).orElse(null);
    }
    
    private String generateToken() {
        return "tok_" + UUID.randomUUID().toString().replace("-", "");
    }
    
    private boolean isValidToken(String deviceId, String token) {
        Optional<Device> deviceOpt = deviceRepository.findById(deviceId);
        if (deviceOpt.isEmpty()) {
            return false;
        }
        
        String expectedToken = deviceOpt.get().getAccessToken();
        return expectedToken != null && expectedToken.equals(token.replace("Bearer ", ""));
    }
}
