package xiaozhi.modules.device.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.utils.Result;

/**
 * Provisioning endpoint for issuing device tokens (simple implementation for testing).
 */
@Tag(name = "Provisioning")
@AllArgsConstructor
@RestController
@RequestMapping
public class ProvisionController {
    private final RedisUtils redisUtils;

    @PostMapping("/provision")
    @Operation(summary = "Issue a device token (provision)")
    public Result<String> provisionDevice(@RequestHeader(value = "Provision-Admin-Key", required = false) String adminKey,
            @RequestBody Map<String, String> body) {
        // Simple admin key check (configured via environment variable PROVISION_ADMIN_KEY)
        String secret = System.getenv("PROVISION_ADMIN_KEY");
        if (secret != null && secret.length() > 0) {
            if (adminKey == null || !secret.equals(adminKey)) {
                return new Result<String>().error("401", "invalid provision admin key");
            }
        }

        String deviceId = body.getOrDefault("device_id", body.get("deviceId"));
        if (deviceId == null || deviceId.isBlank()) {
            return new Result<String>().error("400", "device_id is required");
        }

        // Generate a simple token (UUID) and store in redis for 1 hour
        String token = java.util.UUID.randomUUID().toString();
        try {
            String key = "device:jwt:" + deviceId;
            redisUtils.set(key, token, RedisUtils.HOUR_ONE_EXPIRE);
        } catch (Exception e) {
            // ignore redis errors but still return token
        }

        return new Result<String>().ok(token);
    }
}


