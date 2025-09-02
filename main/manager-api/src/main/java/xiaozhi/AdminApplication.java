package xiaozhi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

import java.net.Socket;
import java.net.InetSocketAddress;
import java.net.UnknownHostException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootApplication
public class AdminApplication {

    public static void main(String[] args) {
        // Print debug info BEFORE attempting to start Spring so logs appear even if startup fails
        System.out.println("http://localhost:8002/xiaozhi/doc.html");
        try {
            // Environment via System.getenv as fallback if context cannot be created
            String url = System.getenv().getOrDefault("SPRING_DATASOURCE_DRUID_URL", System.getenv().getOrDefault("SPRING_DATASOURCE_URL", System.getenv().getOrDefault("SPRING_DATASOURCE_URL", null)));
            String user = System.getenv().getOrDefault("SPRING_DATASOURCE_DRUID_USERNAME", System.getenv().getOrDefault("SPRING_DATASOURCE_USERNAME", "null"));
            String liq = System.getenv().getOrDefault("SPRING_LIQUIBASE_ENABLED", System.getenv().getOrDefault("spring.liquibase.enabled", "null"));
            System.out.println("[DEBUG] SPRING_DATASOURCE_DRUID_URL=" + url);
            System.out.println("[DEBUG] SPRING_DATASOURCE_DRUID_USERNAME=" + user);
            System.out.println("[DEBUG] SPRING_LIQUIBASE_ENABLED=" + liq);
            System.out.println("[DEBUG] JAVA_OPTS=" + System.getenv("JAVA_OPTS"));
            System.out.println("[DEBUG] System properties: java.net.preferIPv4Stack=" + System.getProperty("java.net.preferIPv4Stack") + " java.net.preferIPv6Addresses=" + System.getProperty("java.net.preferIPv6Addresses"));

            if (url != null && url.startsWith("jdbc:postgresql://")) {
                try {
                    String hostport = url.substring("jdbc:postgresql://".length());
                    int slash = hostport.indexOf('/');
                    if (slash != -1) hostport = hostport.substring(0, slash);
                    int q = hostport.indexOf('?');
                    if (q != -1) hostport = hostport.substring(0, q);
                    String host = hostport;
                    int port = 5432;
                    if (hostport.contains(":")) {
                        String[] parts = hostport.split(":");
                        host = parts[0];
                        port = Integer.parseInt(parts[1]);
                    }
                    System.out.println("[DEBUG] Testing TCP to " + host + ":" + port);
                    try (Socket s = new Socket()) {
                        s.connect(new InetSocketAddress(host, port), 5000);
                        System.out.println("[DEBUG] TCP_CONNECT_OK");
                    } catch (Exception e) {
                        System.out.println("[DEBUG] TCP_CONNECT_ERR: " + e.toString());
                        if (e instanceof UnknownHostException) {
                            // Try DNS-over-HTTPS (Cloudflare) to fetch A records and attempt IPv4 connect
                            try {
                                List<String> ips = fetchARecordsViaDoH(host);
                                for (String ip : ips) {
                                    try (Socket s2 = new Socket()) {
                                        System.out.println("[DEBUG] Trying IPv4 " + ip + ":" + port);
                                        s2.connect(new InetSocketAddress(ip, port), 5000);
                                        System.out.println("[DEBUG] TCP_CONNECT_OK_VIA_IPV4:" + ip);
                                        break;
                                    } catch (Exception ex2) {
                                        System.out.println("[DEBUG] IPv4_CONNECT_ERR " + ip + " -> " + ex2.toString());
                                    }
                                }
                            } catch (Exception dohEx) {
                                System.out.println("[DEBUG] DOH_ERR: " + dohEx.toString());
                            }
                        }
                    }
                } catch (Exception e) {
                    System.out.println("[DEBUG] PARSE_URL_ERR: " + e.toString());
                }
            } else {
                System.out.println("[DEBUG] No JDBC URL detected to test.");
            }
        } catch (Exception e) {
            System.out.println("[DEBUG] PRESTART_ERR: " + e.toString());
        }

        // Now start Spring; if it fails, we will catch and print the stacktrace to logs
        try {
            ApplicationContext ctx = SpringApplication.run(AdminApplication.class, args);
        } catch (Throwable t) {
            System.out.println("[ERROR] SpringApplication failed: " + t.toString());
            t.printStackTrace(System.out);
            throw t;
        }
    }

    private static List<String> fetchARecordsViaDoH(String host) throws Exception {
        // Cloudflare DoH JSON endpoint
        String url = "https://cloudflare-dns.com/dns-query?name=" + host + "&type=A";
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest req = HttpRequest.newBuilder().uri(URI.create(url)).header("accept", "application/dns-json").GET().build();
        HttpResponse<String> res = client.send(req, HttpResponse.BodyHandlers.ofString());
        ObjectMapper om = new ObjectMapper();
        JsonNode root = om.readTree(res.body());
        List<String> ips = new ArrayList<>();
        if (root.has("Answer")) {
            for (JsonNode a : root.get("Answer")) {
                String data = a.get("data").asText();
                // Only A records
                if (data != null && data.contains(".")) ips.add(data);
            }
        }
        return ips;
    }
}