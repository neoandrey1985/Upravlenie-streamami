package com.planirovanie.org;

import com.planirovanie.entity.UserSession;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Organisation structure API. GET /api/org — any signed-in user (sees only accessible teams);
 * every mutation — ADMIN only (enforced in {@code AuthInterceptor}).
 */
@RestController
@RequestMapping("/api/org")
public class OrgController {
    private final OrgService org;

    public OrgController(OrgService org) { this.org = org; }

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
