package com.planirovanie;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.planirovanie.service.AuthService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Stream document (features, PI, ROAM, Scrum of Scrums): versioning, conflicts and stream-level roles. */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "app.auth.enabled=true",
        "app.auth.seed-defaults=true",
        "spring.datasource.url=jdbc:h2:mem:streams_doc;MODE=PostgreSQL;DB_CLOSE_DELAY=-1"
})
class StreamDocTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper om;
    @Autowired AuthService auth;

    private String login(String user, String pass) throws Exception {
        MvcResult r = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + user + "\",\"password\":\"" + pass + "\"}"))
                .andExpect(status().isOk()).andReturn();
        return json(r).get("token").asText();
    }

    private static MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder b, String token) {
        return b.header("Authorization", "Bearer " + token).contentType(MediaType.APPLICATION_JSON);
    }

    private JsonNode json(MvcResult r) throws Exception {
        return om.readTree(r.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    private static String doc(String feature, long base) {
        return "{\"baseVersion\":" + base + ",\"data\":{\"features\":[{\"id\":\"F-1\",\"name\":\"" + feature + "\"}],\"roam\":[]}}";
    }

    @Test
    void versionedStreamDocumentWithStreamRoles() throws Exception {
        String admin = login("admin", "admin123");

        // empty document of the default stream
        JsonNode d0 = json(mvc.perform(as(get("/api/org/streams/s1/doc"), admin)).andExpect(status().isOk()).andReturn());
        assertEquals(0, d0.get("version").asLong());
        assertTrue(d0.get("data").isNull());
        assertEquals("ADMIN", d0.get("role").asText());

        // save, read back, stale write -> 409 with the current document
        assertEquals(1, json(mvc.perform(as(put("/api/org/streams/s1/doc"), admin).content(doc("Оплата картой", 0)))
                .andExpect(status().isOk()).andReturn()).get("version").asLong());
        JsonNode d1 = json(mvc.perform(as(get("/api/org/streams/s1/doc"), admin)).andExpect(status().isOk()).andReturn());
        assertEquals("Оплата картой", d1.get("data").get("features").get(0).get("name").asText());
        JsonNode conflict = json(mvc.perform(as(put("/api/org/streams/s1/doc"), admin).content(doc("Устаревшая", 0)))
                .andExpect(status().isConflict()).andReturn());
        assertEquals(1, conflict.get("version").asLong());
        assertEquals("Оплата картой", conflict.get("data").get("features").get(0).get("name").asText());
        mvc.perform(as(get("/api/org/streams/s404/doc"), admin)).andExpect(status().isNotFound());

        // users without memberships: global role (editor writes, viewer reads only)
        String editor = login("editor", "editor123"), viewer = login("viewer", "viewer123");
        mvc.perform(as(put("/api/org/streams/s1/doc"), editor).content(doc("E", 1))).andExpect(status().isOk());
        mvc.perform(as(get("/api/org/streams/s1/doc"), viewer)).andExpect(status().isOk());
        mvc.perform(as(put("/api/org/streams/s1/doc"), viewer).content(doc("V", 2))).andExpect(status().isForbidden());

        // stream EDITOR membership: may edit the stream document of its stream, nothing outside it
        String s2 = json(mvc.perform(as(post("/api/org/streams"), admin).content("{\"name\":\"Логистика\"}"))
                .andExpect(status().isOk()).andReturn()).get("id").asText();
        auth.create("rte", "Rte-pass-1234", "VIEWER", "RTE");
        mvc.perform(as(post("/api/org/memberships"), admin)
                .content("{\"username\":\"rte\",\"scopeType\":\"STREAM\",\"scopeId\":\"" + s2 + "\",\"role\":\"EDITOR\"}"))
                .andExpect(status().isOk());
        String rte = login("rte", "Rte-pass-1234");
        mvc.perform(as(put("/api/org/streams/" + s2 + "/doc"), rte).content(doc("Склад", 0))).andExpect(status().isOk());
        mvc.perform(as(get("/api/org/streams/s1/doc"), rte)).andExpect(status().isForbidden());
        mvc.perform(as(post("/api/org/streams"), rte).content("{\"name\":\"x\"}")).andExpect(status().isForbidden());

        // a TEAM member sees the stream document of the team's stream read-only
        auth.create("dev", "Dev-pass-1234", "EDITOR", "Dev");
        mvc.perform(as(post("/api/org/memberships"), admin)
                .content("{\"username\":\"dev\",\"scopeType\":\"TEAM\",\"scopeId\":\"t1\",\"role\":\"EDITOR\"}"))
                .andExpect(status().isOk());
        String dev = login("dev", "Dev-pass-1234");
        JsonNode devDoc = json(mvc.perform(as(get("/api/org/streams/s1/doc"), dev)).andExpect(status().isOk()).andReturn());
        assertEquals("VIEWER", devDoc.get("role").asText());
        mvc.perform(as(put("/api/org/streams/s1/doc"), dev).content(doc("D", 2))).andExpect(status().isForbidden());
        mvc.perform(as(get("/api/org/streams/" + s2 + "/doc"), dev)).andExpect(status().isForbidden());

        // deleting an empty stream removes its document too
        mvc.perform(as(delete("/api/org/streams/" + s2), admin)).andExpect(status().isNoContent());
        mvc.perform(as(get("/api/org/streams/" + s2 + "/doc"), admin)).andExpect(status().isNotFound());
    }
}
