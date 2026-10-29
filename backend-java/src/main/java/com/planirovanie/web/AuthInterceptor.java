package com.planirovanie.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.planirovanie.entity.UserSession;
import com.planirovanie.org.OrgService;
import com.planirovanie.org.OrgTeam;
import com.planirovanie.org.TenantContext;
import com.planirovanie.service.AuditService;
import com.planirovanie.service.AuthService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.util.Map;
import java.util.Optional;

/**
 * Enforces authentication and role-based authorization on every /api request:
 *   - public: login, health, CORS preflight, and the HEAD probe on /api/state;
 *   - reads (GET): any authenticated user (VIEWER+);
 *   - writes (POST/PUT/DELETE/PATCH): EDITOR or ADMIN;
 *   - /api/auth/me, /api/auth/me/password: any authenticated user (own profile only);
 *   - /api/auth/users**: ADMIN only;
 *   - /api/org: reads — any signed-in user, mutations — ADMIN only (stream documents: stream role);
 *   - team-scoped data (/api/state, /api/tasks): the team comes from the X-Team-Id header (or ?team=),
 *     access and write rights follow the user's EFFECTIVE role on that team (see {@link OrgService}),
 *     and the request runs in that team's schema ({@link TenantContext}).
 * The resolved {@link UserSession} is exposed to controllers as request attribute "session".
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    private final AuthService auth;
    private final AuditService audit;
    private final OrgService org;
    private final ObjectMapper json = new ObjectMapper();

    @Value("${app.auth.enabled:true}")
    private boolean enabled;

    public AuthInterceptor(AuthService auth, AuditService audit, OrgService org) {
        this.auth = auth;
        this.audit = audit;
        this.org = org;
    }

    @Override
    public boolean preHandle(HttpServletRequest req, HttpServletResponse res, Object handler) throws Exception {
        req.setAttribute("t0", System.currentTimeMillis());
        TenantContext.clear();                                           // pooled threads: never inherit a team
        String method = req.getMethod();
        if ("OPTIONS".equals(method)) return true;                       // CORS preflight

        String path = req.getRequestURI();
        // Always-public endpoints.
        if (path.endsWith("/api/health")) return true;
        if (path.endsWith("/api/auth/login")) return true;
        if (path.endsWith("/api/state") && "HEAD".equals(method)) return true;   // backend-presence probe

        // Resolve the bearer token (if any) so controllers can read the current user.
        Optional<UserSession> session = auth.resolve(bearer(req));
        session.ifPresent(s -> req.setAttribute("session", s));

        boolean teamScoped = path.endsWith("/api/state") || path.contains("/api/tasks");

        if (!enabled) return !teamScoped || enterTeam(req, res, null, method);   // auth disabled (e.g. tests/dev)

        if (session.isEmpty()) return deny(res, 401, "unauthorized");
        if (teamScoped) return enterTeam(req, res, session.get(), method);

        String role = session.get().role;
        boolean writing = method.equals("POST") || method.equals("PUT")
                || method.equals("DELETE") || method.equals("PATCH");

        // Own profile (member binding, password change): any signed-in user, incl. VIEWER.
        if (path.endsWith("/api/auth/me") || path.endsWith("/api/auth/me/password")) return true;
        // ADMIN-only surface: user & role management.
        if (path.contains("/api/auth/users")) {
            return "ADMIN".equals(role) ? true : deny(res, 403, "forbidden");
        }
        // Client-side event ingest: any signed-in user (incl. VIEWER) may record UI events.
        if (path.contains("/api/audit/client")) return true;
        // Organisation structure: everyone reads (filtered by access), only ADMIN changes it.
        if (path.contains("/api/org")) {
            if (path.endsWith("/doc") || path.endsWith("/vote")) return true;   // stream document / team vote: checked in OrgController
            return !writing || "ADMIN".equals(role) ? true : deny(res, 403, "forbidden");
        }
        // Reading the audit log is ADMIN-only.
        if (path.contains("/api/audit")) {
            return "ADMIN".equals(role) ? true : deny(res, 403, "forbidden");
        }
        // Any mutation of application data requires EDITOR or ADMIN.
        if (writing && !("EDITOR".equals(role) || "ADMIN".equals(role))) {
            return deny(res, 403, "forbidden");
        }
        return true;
    }

    /** Resolves the requested team, checks the effective role and switches the request to the team's schema. */
    private boolean enterTeam(HttpServletRequest req, HttpServletResponse res, UserSession s, String method) throws Exception {
        String id = req.getHeader("X-Team-Id");
        if (id == null || id.isBlank()) id = req.getParameter("team");
        Optional<OrgTeam> team = org.team(id);
        if (team.isEmpty()) return deny(res, 404, "team_not_found");
        String role = org.effectiveRole(s, team.get());
        if (role == null) return deny(res, 403, "forbidden");
        boolean writing = !("GET".equals(method) || "HEAD".equals(method));
        if (writing && !OrgService.canWrite(role)) return deny(res, 403, "forbidden");
        req.setAttribute("team", team.get().id);
        req.setAttribute("teamRole", role);
        TenantContext.set(OrgService.tenantOf(team.get()));
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest req, HttpServletResponse res, Object handler, Exception ex) {
        TenantContext.clear();
        try {
            if (audit == null || !audit.isEnabled()) return;
            String path = req.getRequestURI();
            String method = req.getMethod();
            if ("OPTIONS".equals(method)) return;
            if (path.contains("/api/audit")) return;                     // don't log the audit endpoints themselves
            Object s = req.getAttribute("session");
            String user = null, role = null;
            if (s instanceof UserSession us) { user = us.username; role = us.role; }
            int status = res.getStatus();
            Object t0 = req.getAttribute("t0");
            Integer dur = (t0 instanceof Long l) ? (int) (System.currentTimeMillis() - l) : null;
            String category = status == 401 || status == 403 ? "DENY" : (status >= 500 ? "ERROR" : "ACCESS");
            audit.log(category, method, user, role, method, path, status, dur,
                    req.getRemoteAddr(), req.getHeader("User-Agent"), null);
        } catch (Exception ignore) { /* logging must never break the response */ }
    }

    private static String bearer(HttpServletRequest req) {
        String h = req.getHeader("Authorization");
        if (h != null && h.regionMatches(true, 0, "Bearer ", 0, 7)) return h.substring(7).trim();
        return req.getHeader("X-Auth-Token");                           // convenience fallback
    }

    private boolean deny(HttpServletResponse res, int status, String error) throws Exception {
        res.setStatus(status);
        res.setContentType("application/json");
        res.getWriter().write(json.writeValueAsString(Map.of("error", error)));
        return false;
    }
}
