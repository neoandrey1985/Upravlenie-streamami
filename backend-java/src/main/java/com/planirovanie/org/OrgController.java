package com.planirovanie.org;

import com.fasterxml.jackson.databind.JsonNode;
import com.planirovanie.entity.UserSession;
import com.planirovanie.service.VersionConflictException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Organisation structure API. GET /api/org — any signed-in user (sees only accessible teams);
 * structure mutations — ADMIN only (enforced in {@code AuthInterceptor}). The stream document
 * (/api/org/streams/{id}/doc) is checked here by the stream-level role ({@link OrgService#streamRole}).
 */
@RestController
@RequestMapping("/api/org")
public class OrgController {
    private final OrgService org;
    private final StreamDocService docs;

    public OrgController(OrgService org, StreamDocService docs) { this.org = org; this.docs = docs; }

    private static UserSession session(HttpServletRequest req) {
        Object s = req.getAttribute("session");
        return s instanceof UserSession us ? us : null;
    }

    @GetMapping
    public Map<String, Object> view(HttpServletRequest req) { return org.view(session(req)); }

    // ----- streams -----

    @PostMapping("/streams")
    public ResponseEntity<?> createStream(@RequestBody Map<String, String> b) {
        return ResponseEntity.ok(org.createStream(b.get("name"), b.get("descr")));
    }

    @PutMapping("/streams/{id}")
    public ResponseEntity<?> updateStream(@PathVariable String id, @RequestBody Map<String, String> b) {
        return org.updateStream(id, b.get("name"), b.get("descr"))
                .<ResponseEntity<?>>map(ResponseEntity::ok).orElse(ResponseEntity.notFound().build());
    }

    @DeleteMapping("/streams/{id}")
    public ResponseEntity<?> deleteStream(@PathVariable String id) {
        return result(org.deleteStream(id));
    }

    // ----- stream document -----

    @GetMapping("/streams/{id}/doc")
    public ResponseEntity<?> getDoc(@PathVariable String id, HttpServletRequest req) {
        if (!org.streamExists(id)) return ResponseEntity.notFound().build();
        String role = org.streamRole(session(req), id);
        if (role == null) return ResponseEntity.status(403).body(Map.of("error", "forbidden"));
        Map<String, Object> r = new java.util.LinkedHashMap<>(docs.get(id));
        r.put("role", role);
        return ResponseEntity.ok(r);
    }

    @PutMapping("/streams/{id}/doc")
    public ResponseEntity<?> putDoc(@PathVariable String id, @RequestBody JsonNode body, HttpServletRequest req) {
        if (!org.streamExists(id)) return ResponseEntity.notFound().build();
        UserSession s = session(req);
        if (!OrgService.canWrite(org.streamRole(s, id))) return ResponseEntity.status(403).body(Map.of("error", "forbidden"));
        Long base = body != null && body.hasNonNull("baseVersion") ? body.get("baseVersion").asLong() : null;
        try {
            long v = docs.put(id, body == null ? null : body.get("data"), base, s == null ? null : s.username);
            return ResponseEntity.ok(Map.of("version", v));
        } catch (VersionConflictException e) {
            Map<String, Object> cur = docs.get(id);
            Map<String, Object> r = new java.util.LinkedHashMap<>();
            r.put("error", "version_conflict"); r.put("version", cur.get("version")); r.put("data", cur.get("data"));
            return ResponseEntity.status(409).body(r);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ----- teams -----

    @PostMapping("/teams")
    public ResponseEntity<?> createTeam(@RequestBody Map<String, String> b) {
        try {
            return ResponseEntity.ok(org.createTeam(b.get("name"), b.get("streamId"), b.get("template"), b.get("source")));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @PutMapping("/teams/{id}")
    public ResponseEntity<?> updateTeam(@PathVariable String id, @RequestBody Map<String, String> b) {
        try {
            return org.updateTeam(id, b.get("name"), b.get("streamId"))
                    .<ResponseEntity<?>>map(ResponseEntity::ok).orElse(ResponseEntity.notFound().build());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @DeleteMapping("/teams/{id}")
    public ResponseEntity<?> deleteTeam(@PathVariable String id) {
        return result(org.deleteTeam(id));
    }

    // ----- memberships -----

    @GetMapping("/memberships")
    public ResponseEntity<?> memberships() { return ResponseEntity.ok(org.memberships()); }

    @PostMapping("/memberships")
    public ResponseEntity<?> grant(@RequestBody Map<String, String> b) {
        try {
            return ResponseEntity.ok(org.grant(b.get("username"), b.get("scopeType"), b.get("scopeId"), b.get("role")));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @DeleteMapping("/memberships/{pk}")
    public ResponseEntity<?> revoke(@PathVariable long pk) {
        return org.revoke(pk) ? ResponseEntity.noContent().build() : ResponseEntity.notFound().build();
    }

    private static ResponseEntity<?> result(String error) {
        if (error == null) return ResponseEntity.noContent().build();
        if ("not_found".equals(error)) return ResponseEntity.notFound().build();
        return ResponseEntity.status(409).body(Map.of("error", error));
    }
}
