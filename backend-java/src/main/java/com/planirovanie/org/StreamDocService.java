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

    @Transactional
    public void delete(String streamId) {
        docs.findById(streamId).ifPresent(docs::delete);
    }
}
