package xiaozhi.modules.agent.controller;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.utils.Result;

import java.util.Map;

@Tag(name = "AgentMemory")
@AllArgsConstructor
@RestController
@RequestMapping("/agent")
public class AgentMemoryController {
    private final RedisUtils redisUtils;

    @PutMapping("/saveMemory/{deviceId}")
    @Operation(summary = "Save memory for device (short-term)")
    public Result<Void> saveMemory(@PathVariable("deviceId") String deviceId, @RequestBody Map<String, Object> body) {
        String content = (String) body.getOrDefault("content", "");
        if (content == null) content = "";
        String key = "agent:memory:" + deviceId;
        try {
            redisUtils.set(key, content, RedisUtils.HOUR_ONE_EXPIRE);
        } catch (Exception e) {
            return new Result<Void>().error("500", "redis error");
        }
        return new Result<Void>().ok();
    }

    @PutMapping("/queryMemory/{deviceId}")
    @Operation(summary = "Query memory for device (short-term)")
    public Result<String> queryMemory(@PathVariable("deviceId") String deviceId) {
        String key = "agent:memory:" + deviceId;
        try {
            Object v = redisUtils.get(key);
            return new Result<String>().ok(v == null ? "" : String.valueOf(v));
        } catch (Exception e) {
            return new Result<String>().error("500", "redis error");
        }
    }
}


