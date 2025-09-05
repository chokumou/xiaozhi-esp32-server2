package xiaozhi.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class DeviceRegisterResponse {
    @JsonProperty("device_id")
    private String deviceId;
    
    @JsonProperty("access_token")
    private String accessToken;
    
    @JsonProperty("server_url")
    private String serverUrl;

    public DeviceRegisterResponse(String deviceId, String accessToken, String serverUrl) {
        this.deviceId = deviceId;
        this.accessToken = accessToken;
        this.serverUrl = serverUrl;
    }

    // Getters and setters
    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }
    public String getAccessToken() { return accessToken; }
    public void setAccessToken(String accessToken) { this.accessToken = accessToken; }
    public String getServerUrl() { return serverUrl; }
    public void setServerUrl(String serverUrl) { this.serverUrl = serverUrl; }
}
