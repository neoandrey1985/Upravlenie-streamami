package com.planirovanie.org;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.planirovanie.service.VersionConflictException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Stream-level document (features, PI, objectives, ROAM, cross-team dependencies, Scrum of Scrums).
 * Stored as JSON with an optimistic-concurrency version; always in the platform (default) schema.
 */
@Service
public class StreamDocService {
    /** Guard against runaway documents (the whole stream backlog is far below this). */
    public static final int MAX_BYTES = 4 * 1024 * 1024;

    private final OrgStreamDocRepo docs;
    private final ObjectMapper mapper = new ObjectMapper();

    public StreamDocService(OrgStreamDocRepo docs) { this.docs = docs; }

    @Transactional(readOnly = true)
    public Map<String, Object> get(String streamId) {
        Map<String, Object> r = new LinkedHashMap<>();
        OrgStreamDoc d = docs.findById(streamId).orElse(null);
        r.put("version", d == null ? 0L : d.version);
        JsonNode data = null;
        if (d != null && d.data != null && !d.data.isBlank()) {
            try { data = mapper.readTree(d.data); } catch (Exception ignore) {}
        }
        r.put("data", data);
        return r;
    }

    /** Replaces the document; expectedVersion (if given) must match the stored one. Returns the new version. */
    @Transactional
    public long put(String streamId, JsonNode data, Long expectedVersion, String user) {
        OrgStreamDoc d = docs.findForUpdate(streamId).orElseGet(() -> {
            OrgStreamDoc n = new OrgStreamDoc(); n.streamId = streamId; n.version = 0; return n;
        });
        if (expectedVersion != null && expectedVersion != d.version) throw new VersionConflictException(d.version);
        String json;
        try { json = mapper.writeValueAsString(data == null ? mapper.createObjectNode() : data); }
        catch (Exception e) { throw new IllegalArgumentException("bad_document"); }
        if (json.length() > MAX_BYTES) throw new IllegalArgumentException("document_too_large");
        d.data = json;
        d.version = d.version + 1;
        d.updatedAt = Instant.now();
        d.updatedBy = user;
        docs.save(d);
        return d.version;
    }

    /**
     * Голос команды в оценке зрелости стрима: data.mat.rounds[pi].votes[dim][team] = level (1..5; 0 — снять голос).
     * Сливается в документ на сервере под блокировкой строки — участник команды не перезаписывает остальной документ.
     */
    @Transactional
    public Map<String, Object> vote(String streamId, String pi, String team, JsonNode votes, String user) {
        if (pi == null || pi.isBlank() || team == null || votes == null || !votes.isObject()) throw new IllegalArgumentException("bad_vote");
        OrgStreamDoc d = docs.findForUpdate(streamId).orElseGet(() -> {
            OrgStreamDoc n = new OrgStreamDoc(); n.streamId = streamId; n.version = 0; return n;
        });
        com.fasterxml.jackson.databind.node.ObjectNode data;
        try {
            JsonNode cur = d.data == null || d.data.isBlank() ? null : mapper.readTree(d.data);
            data = cur != null && cur.isObject() ? (com.fasterxml.jackson.databind.node.ObjectNode) cur : mapper.createObjectNode();
        } catch (Exception e) { data = mapper.createObjectNode(); }
        com.fasterxml.jackson.databind.node.ObjectNode mat = data.has("mat") && data.get("mat").isObject()
                ? (com.fasterxml.jackson.databind.node.ObjectNode) data.get("mat") : data.putObject("mat");
        com.fasterxml.jackson.databind.node.ArrayNode rounds = mat.has("rounds") && mat.get("rounds").isArray()
                ? (com.fasterxml.jackson.databind.node.ArrayNode) mat.get("rounds") : mat.putArray("rounds");
        com.fasterxml.jackson.databind.node.ObjectNode round = null;
        for (JsonNode r : rounds) if (r.isObject() && pi.equals(r.path("pi").asText())) { round = (com.fasterxml.jackson.databind.node.ObjectNode) r; break; }
        if (round == null) { round = rounds.addObject(); round.put("pi", pi); round.putObject("votes"); round.putObject("final"); round.putObject("notes"); }
        com.fasterxml.jackson.databind.node.ObjectNode vs = round.has("votes") && round.get("votes").isObject()
                ? (com.fasterxml.jackson.databind.node.ObjectNode) round.get("votes") : round.putObject("votes");
        var it = votes.fields();
        while (it.hasNext()) {
            var e = it.next(); int lv = e.getValue().asInt(-1);
            if (lv < 0 || lv > 5 || e.getKey().length() > 40) throw new IllegalArgumentException("bad_vote");
            com.fasterxml.jackson.databind.node.ObjectNode dim = vs.has(e.getKey()) && vs.get(e.getKey()).isObject()
                    ? (com.fasterxml.jackson.databind.node.ObjectNode) vs.get(e.getKey()) : vs.putObject(e.getKey());
            if (lv == 0) dim.remove(team); else dim.put(team, lv);
        }
        try { d.data = mapper.writeValueAsString(data); } catch (Exception e) { throw new IllegalArgumentException("bad_document"); }
        if (d.data.length() > MAX_BYTES) throw new IllegalArgumentException("document_too_large");
        d.version = d.version + 1; d.updatedAt = Instant.now(); d.updatedBy = user;
        docs.save(d);
        Map<String, Object> r = new LinkedHashMap<>(); r.put("version", d.version); r.put("data", data);
        return r;
    }

    @Transactional
    public void delete(String streamId) {
        docs.findById(streamId).ifPresent(docs::delete);
    }
}
