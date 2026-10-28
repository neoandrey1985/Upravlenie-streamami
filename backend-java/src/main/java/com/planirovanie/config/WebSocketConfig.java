package com.planirovanie.config;

import com.planirovanie.entity.UserSession;
import com.planirovanie.org.OrgService;
import com.planirovanie.org.OrgTeam;
import com.planirovanie.service.AuthService;
import com.planirovanie.web.BoardSocketHandler;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.server.HandshakeInterceptor;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;

/** Registers the whiteboard collaboration WebSocket at /ws/board.
 *  When auth is enabled, the handshake REQUIRES a valid bearer session token (?token=),
 *  so anonymous clients cannot read or inject board operations. Allowed origins are
 *  configurable (app.ws.allowed-origins). Each team has its own room (?team=<id>, default — the first
 *  team); joining requires access to that team. */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {
    private final BoardSocketHandler handler;
    private final AuthService auth;
    private final OrgService org;

    @Value("${app.auth.enabled:true}")
    private boolean authEnabled;

    @Value("${app.ws.allowed-origins:*}")
    private String allowedOrigins;

    public WebSocketConfig(BoardSocketHandler handler, AuthService auth, OrgService org) {
        this.handler = handler; this.auth = auth; this.org = org;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        String[] origins = allowedOrigins.split("\\s*,\\s*");
        registry.addHandler(handler, "/ws/board").setAllowedOriginPatterns(origins).addInterceptors(new HandshakeInterceptor() {
            @Override
            public boolean beforeHandshake(ServerHttpRequest req, ServerHttpResponse res, WebSocketHandler h, Map<String, Object> attrs) {
                String q = req.getURI().getQuery();
                String token = param(q, "token"), name = param(q, "name");
                Optional<OrgTeam> team = org.team(param(q, "team"));
                if (team.isEmpty()) { res.setStatusCode(HttpStatus.NOT_FOUND); return false; }
                attrs.put("team", team.get().id);
                if (authEnabled) {
                    Optional<UserSession> us = (token == null || token.isBlank()) ? Optional.empty() : auth.resolve(token);
                    if (us.isEmpty()) {                 // reject unauthenticated / expired handshakes
                        res.setStatusCode(HttpStatus.UNAUTHORIZED);
                        return false;
                    }
                    if (org.effectiveRole(us.get(), team.get()) == null) {   // no access to this team's board
                        res.setStatusCode(HttpStatus.FORBIDDEN);
                        return false;
                    }
                    attrs.put("name", us.get().username);
                    return true;
                }
                // auth disabled (tests/dev): best-effort display name only
                if (token != null && !token.isBlank()) auth.resolve(token).ifPresent(u -> attrs.put("name", u.username));
                if (!attrs.containsKey("name") && name != null && !name.isBlank()) attrs.put("name", name);
                return true;
            }
            @Override
            public void afterHandshake(ServerHttpRequest req, ServerHttpResponse res, WebSocketHandler h, Exception ex) {}
        });
    }

    private static String param(String q, String key) {
        if (q == null) return null;
        for (String kv : q.split("&")) {
            int i = kv.indexOf('=');
            if (i > 0 && kv.substring(0, i).equals(key)) {
                try { return URLDecoder.decode(kv.substring(i + 1), StandardCharsets.UTF_8); }
                catch (Exception e) { return kv.substring(i + 1); }
            }
        }
        return null;
    }
}
