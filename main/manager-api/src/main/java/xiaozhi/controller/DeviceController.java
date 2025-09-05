package xiaozhi.controller;

import org.springframework.web.bind.annotation.*;
import xiaozhi.dto.*;
import xiaozhi.service.DeviceService;

@RestController
@RequestMapping("/device")
public class DeviceController {
    
    private final DeviceService deviceService;
    
    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @PostMapping("/register")
    public ApiResponse<DeviceRegisterResponse> registerDevice(@RequestBody DeviceRegisterRequest request) {
        try {
            DeviceRegisterResponse response = deviceService.registerDevice(request);
            return ApiResponse.ok(response);
        } catch (Exception e) {
            return ApiResponse.error("Device registration failed: " + e.getMessage());
        }
    }

    @PostMapping("/heartbeat")
    public ApiResponse<String> heartbeat(@RequestHeader("Authorization") String token,
                                       @RequestParam String deviceId) {
        try {
            deviceService.updateHeartbeat(deviceId, token);
            return ApiResponse.ok("Heartbeat updated");
        } catch (Exception e) {
            return ApiResponse.error("Heartbeat failed: " + e.getMessage());
        }
    }

    @GetMapping("/status/{deviceId}")
    public ApiResponse<String> getDeviceStatus(@PathVariable String deviceId) {
        try {
            String status = deviceService.getDeviceStatus(deviceId);
            return ApiResponse.ok(status);
        } catch (Exception e) {
            return ApiResponse.error("Failed to get device status: " + e.getMessage());
        }
    }
}
