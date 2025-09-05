package xiaozhi.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import xiaozhi.entity.Firmware;
import java.util.Optional;

@Repository
public interface FirmwareRepository extends JpaRepository<Firmware, Long> {
    
    Optional<Firmware> findByDeviceTypeAndIsLatestTrue(String deviceType);
    
    Optional<Firmware> findByDeviceTypeAndVersion(String deviceType, String version);
}
