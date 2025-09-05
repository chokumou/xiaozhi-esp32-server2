package xiaozhi.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;
import xiaozhi.entity.Device;
import java.util.Optional;

@Repository
public interface DeviceRepository extends JpaRepository<Device, String> {
    
    Optional<Device> findByMacAddress(String macAddress);
    
    Optional<Device> findByAccessToken(String accessToken);
    
    @Query("SELECT d FROM Device d WHERE d.lastHeartbeat < :cutoffTime")
    java.util.List<Device> findOfflineDevices(java.time.LocalDateTime cutoffTime);
}
