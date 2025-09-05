package xiaozhi.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class DeviceRegisterRequest {
    @JsonProperty("mac_address")
    private String macAddress;
    
    @JsonProperty("device_type")
    private String deviceType;
    
    @JsonProperty("firmware_version")
    private String firmwareVersion;
    
    @JsonProperty("provision_key")
    private String provisionKey;

    // Getters and setters
    public String getMacAddress() { return macAddress; }
    public void setMacAddress(String macAddress) { this.macAddress = macAddress; }
    public String getDeviceType() { return deviceType; }
    public void setDeviceType(String deviceType) { this.deviceType = deviceType; }
    public String getFirmwareVersion() { return firmwareVersion; }
    public void setFirmwareVersion(String firmwareVersion) { this.firmwareVersion = firmwareVersion; }
    public String getProvisionKey() { return provisionKey; }
    public void setProvisionKey(String provisionKey) { this.provisionKey = provisionKey; }
}
