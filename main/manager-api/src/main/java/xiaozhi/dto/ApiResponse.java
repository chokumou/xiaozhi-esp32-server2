package xiaozhi.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public class ApiResponse<T> {
    @JsonProperty("code")
    private int code;
    
    @JsonProperty("msg")
    private String msg;
    
    @JsonProperty("data")
    private T data;

    public ApiResponse() {
        this.code = 0;
        this.msg = "success";
    }

    public ApiResponse(T data) {
        this.code = 0;
        this.msg = "success";
        this.data = data;
    }

    public ApiResponse(int code, String msg) {
        this.code = code;
        this.msg = msg;
    }

    public static <T> ApiResponse<T> ok(T data) {
        return new ApiResponse<>(data);
    }

    public static <T> ApiResponse<T> ok() {
        return new ApiResponse<>();
    }

    public static <T> ApiResponse<T> error(String msg) {
        return new ApiResponse<>(500, msg);
    }

    // Getters and setters
    public int getCode() { return code; }
    public void setCode(int code) { this.code = code; }
    public String getMsg() { return msg; }
    public void setMsg(String msg) { this.msg = msg; }
    public T getData() { return data; }
    public void setData(T data) { this.data = data; }
}
