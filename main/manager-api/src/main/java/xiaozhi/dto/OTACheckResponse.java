package xiaozhi.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class OTACheckResponse {
    @JsonProperty("update_available")
    private boolean updateAvailable;
    
    @JsonProperty("latest_version")
    private String latestVersion;
    
    @JsonProperty("download_url")
    private String downloadUrl;
    
    @JsonProperty("file_size")
    private Long fileSize;
    
    @JsonProperty("checksum")
    private String checksum;

    public OTACheckResponse(boolean updateAvailable) {
        this.updateAvailable = updateAvailable;
    }

    public OTACheckResponse(boolean updateAvailable, String latestVersion, String downloadUrl, Long fileSize, String checksum) {
        this.updateAvailable = updateAvailable;
        this.latestVersion = latestVersion;
        this.downloadUrl = downloadUrl;
        this.fileSize = fileSize;
        this.checksum = checksum;
    }

    // Getters and setters
    public boolean isUpdateAvailable() { return updateAvailable; }
    public void setUpdateAvailable(boolean updateAvailable) { this.updateAvailable = updateAvailable; }
    public String getLatestVersion() { return latestVersion; }
    public void setLatestVersion(String latestVersion) { this.latestVersion = latestVersion; }
    public String getDownloadUrl() { return downloadUrl; }
    public void setDownloadUrl(String downloadUrl) { this.downloadUrl = downloadUrl; }
    public Long getFileSize() { return fileSize; }
    public void setFileSize(Long fileSize) { this.fileSize = fileSize; }
    public String getChecksum() { return checksum; }
    public void setChecksum(String checksum) { this.checksum = checksum; }
}
