package xiaozhi.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class WebSocketConfig {
    @JsonProperty("url")
    private String url;
    
    public WebSocketConfig() {
        this.url = "wss://xiaozhi-esp32-server3-production.up.railway.app/ws/";
    }
    
    public String getUrl() {
        return url;
    }
    
    public void setUrl(String url) {
        this.url = url;
    }
}
