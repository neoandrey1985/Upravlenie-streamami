package com.planirovanie.org;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.planirovanie.dto.Dtos.StateDto;
import com.planirovanie.entity.UserSession;
import com.planirovanie.service.StateService;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.*;

/**
 * Organisation structure: Portfolio → Stream → Team, plus per-stream / per-team roles.
 *
 * Access rule (effective role of a user on a team):
 *   - global ADMIN → ADMIN on every team;
 *   - a user WITHOUT any membership → their global role on every team (simple mode, like the base app);
 *   - otherwise → the higher of the TEAM membership and the membership on the team's STREAM; none → no access.
 *
 * Methods that switch tenants are deliberately NOT @Transactional: the JPA session picks its schema
 * when it opens, so each repository / StateService call must open its own session.
 */
@Service
public class OrgService {
    public static final String DEFAULT_TEAM = "t1";
    private static final List<String> RANK = List.of("VIEWER", "EDITOR", "ADMIN");

    private final OrgStreamRepo streams;
    private final OrgTeamRepo teams;
    private final OrgMembershipRepo members;
    private final TeamSchemaManager schemas;
    private final StateService state;
    private final StreamDocService streamDocs;
    private final ObjectMapper mapper = new ObjectMapper();

    public OrgService(OrgStreamRepo streams, OrgTeamRepo teams, OrgMembershipRepo members,
                      TeamSchemaManager schemas, StateService state, StreamDocService streamDocs) {
        this.streams = streams; this.teams = teams; this.members = members; this.schemas = schemas; this.state = state;
        this.streamDocs = streamDocs;
    }

    /** First start: one stream with one team that owns the existing (default-schema) data. */
    @EventListener(ApplicationReadyEvent.class)
    public void seed() {
        if (streams.count() > 0) return;
        OrgStream s = new OrgStream();
        s.id = "s1"; s.name = "Стрим 1"; s.ord = 0; s.createdAt = Instant.now();
        streams.save(s);
        OrgTeam t = new OrgTeam();
        t.id = DEFAULT_TEAM; t.streamId = s.id; t.name = "Команда 1"; t.schemaName = null; t.ord = 0; t.createdAt = Instant.now();
        teams.save(t);
    }

    // ---------- lookups & access ----------

    public Optional<OrgTeam> team(String id) {
        return teams.findById(id == null || id.isBlank() ? DEFAULT_TEAM : id);
    }

    /** Physical schema of the team for {@link TenantContext} (null = default schema). */
    public static String tenantOf(OrgTeam t) { return t.schemaName; }

    /** Effective role on the team, or null if the user may not see it. Null session = auth disabled. */
    public String effectiveRole(UserSession s, OrgTeam t) {
        if (s == null) return "EDITOR";
        if ("ADMIN".equals(s.role)) return "ADMIN";
        List<OrgMembership> mine = members.findByUsername(s.username);
        if (mine.isEmpty()) return s.role;
        String best = null;
        for (OrgMembership m : mine) {
            boolean hit = ("TEAM".equals(m.scopeType) && m.scopeId.equals(t.id))
                    || ("STREAM".equals(m.scopeType) && m.scopeId.equals(t.streamId));
            if (hit) best = max(best, m.role);
        }
        return best;
    }

    /**
     * Effective role on the STREAM level (stream document: features, PI, ROAM, Scrum of Scrums):
     * ADMIN → ADMIN; no memberships → global role; a STREAM membership → its role;
     * otherwise any TEAM membership inside the stream → VIEWER (team members see their stream); else null.
     */
    public String streamRole(UserSession s, String streamId) {
        if (s == null) return "EDITOR";
        if ("ADMIN".equals(s.role)) return "ADMIN";
        List<OrgMembership> mine = members.findByUsername(s.username);
        if (mine.isEmpty()) return s.role;
        String best = null;
        for (OrgMembership m : mine) {
            if ("STREAM".equals(m.scopeType) && m.scopeId.equals(streamId)) best = max(best, m.role);
        }
        if (best != null) return best;
        for (OrgMembership m : mine) {
            if ("TEAM".equals(m.scopeType) && teams.findById(m.scopeId).map(t -> streamId.equals(t.streamId)).orElse(false)) return "VIEWER";
        }
        return null;
    }

    public boolean streamExists(String id) { return id != null && streams.existsById(id); }

    public static boolean canWrite(String role) { return "EDITOR".equals(role) || "ADMIN".equals(role); }

    private static String max(String a, String b) {
        if (a == null) return b;
        if (b == null) return a;
        return RANK.indexOf(a) >= RANK.indexOf(b) ? a : b;
    }

    /** The structure visible to the user: accessible teams (with the effective role) and their streams. */
    public Map<String, Object> view(UserSession s) {
        List<Map<String, Object>> tl = new ArrayList<>();
        Set<String> visibleStreams = new LinkedHashSet<>();
        for (OrgTeam t : teams.findAllByOrderByOrdAsc()) {
            String role = effectiveRole(s, t);
            if (role == null) continue;
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", t.id); m.put("name", t.name); m.put("streamId", t.streamId); m.put("role", role);
            tl.add(m);
            visibleStreams.add(t.streamId);
        }
        boolean admin = s == null || "ADMIN".equals(s.role);
        List<Map<String, Object>> sl = new ArrayList<>();
        for (OrgStream st : streams.findAllByOrderByOrdAsc()) {
            if (!admin && !visibleStreams.contains(st.id)) continue;
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", st.id); m.put("name", st.name); m.put("descr", st.descr);
            sl.add(m);
        }
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("streams", sl);
        r.put("teams", tl);
        r.put("defaultTeam", tl.isEmpty() ? null : tl.get(0).get("id"));
        r.put("canManage", admin);
        return r;
    }

    // ---------- streams ----------

    public OrgStream createStream(String name, String descr) {
        OrgStream s = new OrgStream();
        s.id = nextId("s", streams.findAll().stream().map(x -> x.id).toList());
        s.name = clean(name, "Новый стрим"); s.descr = descr; s.ord = (int) streams.count(); s.createdAt = Instant.now();
        return streams.save(s);
    }

    public Optional<OrgStream> updateStream(String id, String name, String descr) {
        return streams.findById(id).map(s -> {
            if (name != null) s.name = clean(name, s.name);
            if (descr != null) s.descr = descr;
            return streams.save(s);
        });
    }

    /** Deletes an EMPTY stream. Returns an error code or null on success. */
    public String deleteStream(String id) {
        if (streams.findById(id).isEmpty()) return "not_found";
        if (!teams.findByStreamId(id).isEmpty()) return "stream_not_empty";
        members.deleteAll(members.findByScopeTypeAndScopeId("STREAM", id));
        streamDocs.delete(id);
        streams.deleteById(id);
        return null;
    }

    // ---------- teams ----------

    /**
     * Creates a team with its own schema. template: "empty" (reference data of the source team, no work items)
     * or "copy" (full copy of the source team's data). Source defaults to the first team.
     */
    public OrgTeam createTeam(String name, String streamId, String template, String sourceTeam) {
        if (streamId == null || streams.findById(streamId).isEmpty()) throw new IllegalArgumentException("stream_not_found");
        OrgTeam src = team(sourceTeam).orElseThrow(() -> new IllegalArgumentException("source_not_found"));
        OrgTeam t = new OrgTeam();
        t.id = nextId("t", teams.findAll().stream().map(x -> x.id).toList());
        t.streamId = streamId; t.name = clean(name, "Новая команда");
        t.schemaName = schemas.schemaFor(t.id);
        t.ord = (int) teams.count(); t.createdAt = Instant.now();

        schemas.provision(t.schemaName);
        try {
            StateDto s = TenantContext.callAs(tenantOf(src), state::get);
            if (!"copy".equals(template)) blank(s);
            if (s.params != null) s.params.name = t.name;
            TenantContext.callAs(t.schemaName, () -> state.replace(s, null));
            return teams.save(t);
        } catch (RuntimeException e) {
            try { schemas.drop(t.schemaName); } catch (Exception ignore) {}
            throw e;
        }
    }

    public Optional<OrgTeam> updateTeam(String id, String name, String streamId) {
        return teams.findById(id).map(t -> {
            if (name != null) t.name = clean(name, t.name);
            if (streamId != null) {
                if (streams.findById(streamId).isEmpty()) throw new IllegalArgumentException("stream_not_found");
                t.streamId = streamId;
            }
            return teams.save(t);
        });
    }

    /** Deletes a team and its schema. The first (default-schema) team cannot be deleted. */
    public String deleteTeam(String id) {
        Optional<OrgTeam> o = teams.findById(id);
        if (o.isEmpty()) return "not_found";
        OrgTeam t = o.get();
        if (t.schemaName == null) return "default_team";
        schemas.drop(t.schemaName);
        members.deleteAll(members.findByScopeTypeAndScopeId("TEAM", id));
        teams.delete(t);
        return null;
    }

    // ---------- memberships ----------

    public List<OrgMembership> memberships() { return members.findAll(); }

    public OrgMembership grant(String username, String scopeType, String scopeId, String role) {
        if (username == null || username.isBlank()) throw new IllegalArgumentException("username_required");
        if (!"STREAM".equals(scopeType) && !"TEAM".equals(scopeType)) throw new IllegalArgumentException("bad_scope");
        if (!"VIEWER".equals(role) && !"EDITOR".equals(role)) throw new IllegalArgumentException("bad_role");
        boolean exists = "STREAM".equals(scopeType) ? streams.existsById(scopeId) : teams.existsById(scopeId);
        if (!exists) throw new IllegalArgumentException("scope_not_found");
        OrgMembership m = members.findByUsername(username).stream()
                .filter(x -> x.scopeType.equals(scopeType) && x.scopeId.equals(scopeId)).findFirst()
                .orElseGet(OrgMembership::new);
        m.username = username.trim(); m.scopeType = scopeType; m.scopeId = scopeId; m.role = role;
        return members.save(m);
    }

    public boolean revoke(long pk) {
        if (!members.existsById(pk)) return false;
        members.deleteById(pk);
        return true;
    }

    // ---------- helpers ----------

    /** Keeps the team's reference data (DoD, DoR, holidays, FAQ, Ishikawa categories); clears the work items. */
    private void blank(StateDto s) {
        var dod = s.dod; var dor = s.dorItems; var cal = s.calendar; var faq = s.faq; var cats = s.ishikawaCats;
        var params = s.params; var budget = s.budget; var ttm = s.ttmTarget;
        for (var f : StateDto.class.getFields()) {
            if (List.class.isAssignableFrom(f.getType())) {
                try { f.set(s, new ArrayList<>()); } catch (IllegalAccessException ignore) {}
            }
        }
        s.dod = dod; s.dorItems = dor; s.calendar = cal; s.faq = faq; s.ishikawaCats = cats;
        s.params = params; s.budget = budget; s.ttmTarget = ttm;
        if (s.params != null) s.params.goal = "";
        s.board = mapper.createObjectNode().set("items", mapper.createArrayNode());   // empty board (client adds cam)
    }

    private static String nextId(String prefix, List<String> ids) {
        int max = 0;
        for (String id : ids) {
            if (id != null && id.startsWith(prefix)) {
                try { max = Math.max(max, Integer.parseInt(id.substring(prefix.length()))); } catch (NumberFormatException ignore) {}
            }
        }
        return prefix + (max + 1);
    }

    private static String clean(String v, String dflt) {
        if (v == null) return dflt;
        String s = v.trim();
        if (s.length() > 120) s = s.substring(0, 120);
        return s.isEmpty() ? dflt : s;
    }
}
