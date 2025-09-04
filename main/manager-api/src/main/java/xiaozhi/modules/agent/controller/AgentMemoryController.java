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
        // Try Redis first
        String key = "agent:memory:" + deviceId;
        try {
            redisUtils.set(key, content, RedisUtils.HOUR_ONE_EXPIRE);
        } catch (Exception e) {
            // ignore redis errors and fallback to supabase
        }

        // Also persist to Supabase via REST if configured
        String supabaseUrl = System.getenv("SUPABASE_URL");
        String supabaseKey = System.getenv("SUPABASE_SERVICE_ROLE_KEY");
        if (supabaseUrl != null && supabaseKey != null) {
            try {
                String target = supabaseUrl + "/rest/v1/agent_memory";
                String json = String.format("{\"device_id\":\"%s\",\"content\":\"%s\"}", deviceId, content.replace("\"","\\\""));
                java.net.http.HttpRequest req = java.net.http.HttpRequest.newBuilder()
                        .uri(java.net.URI.create(target))
                        .header("apikey", supabaseKey)
                        .header("Authorization", "Bearer " + supabaseKey)
                        .header("Content-Type", "application/json")
                        .POST(java.net.http.HttpRequest.BodyPublishers.ofString(json))
                        .build();
                java.net.http.HttpClient.newHttpClient().send(req, java.net.http.HttpResponse.BodyHandlers.discarding());
            } catch (Exception ex) {
                // log but don't fail
            }
        }

        return new Result<Void>().ok();
    }

    @PutMapping("/queryMemory/{deviceId}")
    @Operation(summary = "Query memory for device (short-term)")
    public Result<String> queryMemory(@PathVariable("deviceId") String deviceId) {
        String key = "agent:memory:" + deviceId;
        try {
            Object v = redisUtils.get(key);
            if (v != null) return new Result<String>().ok(String.valueOf(v));
        } catch (Exception e) {
            // ignore and fallback to supabase
        }

        // fallback to supabase REST
        String supabaseUrl = System.getenv("SUPABASE_URL");
        String supabaseKey = System.getenv("SUPABASE_SERVICE_ROLE_KEY");
        if (supabaseUrl != null && supabaseKey != null) {
            try {
                String target = supabaseUrl + "/rest/v1/agent_memory?device_id=eq." + java.net.URLEncoder.encode(deviceId, java.nio.charset.StandardCharsets.UTF_8);
                java.net.http.HttpRequest req = java.net.http.HttpRequest.newBuilder()
                        .uri(java.net.URI.create(target))
                        .header("apikey", supabaseKey)
                        .header("Authorization", "Bearer " + supabaseKey)
                        .GET()
                        .build();
                java.net.http.HttpResponse<String> res = java.net.http.HttpClient.newHttpClient().send(req, java.net.http.HttpResponse.BodyHandlers.ofString());
                if (res.statusCode() == 200) {
                    String body = res.body();
                    // naive parse: return first object's content field if exists
                    int idx = body.indexOf("\"content\":");
                    if (idx != -1) {
                        int start = body.indexOf('"', idx + 10) + 1;
                        int end = body.indexOf('"', start);
                        if (start>0 && end>start) {
                            String content = body.substring(start, end);
                            return new Result<String>().ok(content);
                        }
                    }
                    return new Result<String>().ok(body);
                }
            } catch (Exception ex) {
                // ignore
            }
        }

        return new Result<String>().ok("");
    }
}


