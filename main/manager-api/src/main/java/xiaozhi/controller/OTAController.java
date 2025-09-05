package xiaozhi.controller;

import org.springframework.web.bind.annotation.*;
import xiaozhi.dto.*;
import xiaozhi.service.OTAService;

@RestController
@RequestMapping("/otaMag")
public class OTAController {
    
    private final OTAService otaService;
    
    public OTAController(OTAService otaService) {
        this.otaService = otaService;
    }

    @GetMapping("/health")
    public ApiResponse<String> health() {
        return ApiResponse.ok("manager-api is running");
    }

    @PostMapping("/check")
    public ApiResponse<OTACheckResponse> checkUpdate(@RequestBody OTACheckRequest request) {
        try {
            OTACheckResponse response = otaService.checkUpdate(request);
            return ApiResponse.ok(response);
        } catch (Exception e) {
            return ApiResponse.error("OTA check failed: " + e.getMessage());
        }
    }

    @GetMapping("/getDownloadUrl")
    public ApiResponse<String> getDownloadUrl(
            @RequestParam(required = false) String version,
            @RequestParam(required = false) String deviceType) {
        
        try {
            String downloadUrl = otaService.getDownloadUrl(version, deviceType);
            return ApiResponse.ok(downloadUrl);
        } catch (Exception e) {
            return ApiResponse.error("Failed to get download URL: " + e.getMessage());
        }
    }

    @PostMapping("/uploadFirmware")
    public ApiResponse<String> uploadFirmware() {
        return ApiResponse.ok("Firmware upload not implemented in simple mode");
    }

    @GetMapping("/version")
    public ApiResponse<String> getVersion() {
        return ApiResponse.ok("1.0.0");
    }
}
