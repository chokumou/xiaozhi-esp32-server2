package xiaozhi.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class OTACheckRequest {
    @JsonProperty("device_id")
    private String deviceId;
    
    @JsonProperty("current_version")
    private String currentVersion;
    
    @JsonProperty("device_type")
    private String deviceType;

    // Getters and setters
    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }
    public String getCurrentVersion() { return currentVersion; }
    public void setCurrentVersion(String currentVersion) { this.currentVersion = currentVersion; }
    public String getDeviceType() { return deviceType; }
    public void setDeviceType(String deviceType) { this.deviceType = deviceType; }
}
