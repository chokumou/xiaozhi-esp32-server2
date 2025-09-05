package xiaozhi.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "firmware")
public class Firmware {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(name = "version", nullable = false)
    private String version;
    
    @Column(name = "device_type", nullable = false)
    private String deviceType;
    
    @Column(name = "download_url", nullable = false)
    private String downloadUrl;
    
    @Column(name = "file_size")
    private Long fileSize;
    
    @Column(name = "checksum")
    private String checksum;
    
    @Column(name = "is_latest")
    private Boolean isLatest = false;
    
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    public Firmware() {}

    public Firmware(String version, String deviceType, String downloadUrl, Long fileSize, String checksum, Boolean isLatest) {
        this.version = version;
        this.deviceType = deviceType;
        this.downloadUrl = downloadUrl;
        this.fileSize = fileSize;
        this.checksum = checksum;
        this.isLatest = isLatest;
        this.createdAt = LocalDateTime.now();
    }

    // Getters and setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }
    public String getDeviceType() { return deviceType; }
    public void setDeviceType(String deviceType) { this.deviceType = deviceType; }
    public String getDownloadUrl() { return downloadUrl; }
    public void setDownloadUrl(String downloadUrl) { this.downloadUrl = downloadUrl; }
    public Long getFileSize() { return fileSize; }
    public void setFileSize(Long fileSize) { this.fileSize = fileSize; }
    public String getChecksum() { return checksum; }
    public void setChecksum(String checksum) { this.checksum = checksum; }
    public Boolean getIsLatest() { return isLatest; }
    public void setIsLatest(Boolean isLatest) { this.isLatest = isLatest; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
