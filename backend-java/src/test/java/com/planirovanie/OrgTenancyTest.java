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

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Streams & teams: schema-per-team isolation, team templates, per-team / per-stream roles, deletion rules. */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "app.auth.enabled=true",
        "app.auth.seed-defaults=true",
        "spring.datasource.url=jdbc:h2:mem:streams_org;MODE=PostgreSQL;DB_CLOSE_DELAY=-1"
})
class OrgTenancyTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper om;
    @Autowired AuthService auth;

    private String login(String user, String pass) throws Exception {
        MvcResult r = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + user + "\",\"password\":\"" + pass + "\"}"))
                .andExpect(status().isOk()).andReturn();
        return om.readTree(r.getResponse().getContentAsString()).get("token").asText();
    }

    private static MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder b, String token, String team) {
        b.header("Authorization", "Bearer " + token);
        if (team != null) b.header("X-Team-Id", team);
        return b.contentType(MediaType.APPLICATION_JSON);
    }

    private JsonNode json(MvcResult r) throws Exception { return om.readTree(r.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8)); }

    private JsonNode state(String token, String team) throws Exception {
        return json(mvc.perform(as(get("/api/state"), token, team)).andExpect(status().isOk()).andReturn()).get("state");
    }

    private static String stateWith(String title) {
        return "{\"state\":{\"params\":{\"name\":\"N\",\"start\":\"2026-08-03\",\"sprintDays\":10,\"focus\":0.8,\"today\":\"2026-09-10\",\"goal\":\"G\",\"sprints\":11},"
             + "\"tasks\":[{\"id\":\"T-99\",\"title\":\"" + title + "\",\"role\":\"Backend\",\"type\":\"Задача\",\"est\":3,\"status\":\"Готово\",\"sprint\":1}]}}";
    }

    @Test
    void streamsTeamsIsolationAndRoles() throws Exception {
        String admin = login("admin", "admin123");

        // first start: one stream with one team that owns the existing data
        JsonNode org = json(mvc.perform(as(get("/api/org"), admin, null)).andExpect(status().isOk()).andReturn());
        assertEquals("t1", org.get("defaultTeam").asText());
        assertTrue(org.get("canManage").asBoolean());
        assertEquals("s1", org.get("streams").get(0).get("id").asText());

        // team-1 data before anything else happens
        mvc.perform(as(put("/api/state"), admin, "t1").content(stateWith("Задача команды 1"))).andExpect(status().isOk());
        assertEquals("Задача команды 1", state(admin, "t1").get("tasks").get(0).get("title").asText());

        // admin creates a stream and an EMPTY team in it: own schema, reference data only
        String s2 = json(mvc.perform(as(post("/api/org/streams"), admin, null).content("{\"name\":\"Платежи\"}"))
                .andExpect(status().isOk()).andReturn()).get("id").asText();
        JsonNode t2 = json(mvc.perform(as(post("/api/org/teams"), admin, null)
                .content("{\"name\":\"Касса\",\"streamId\":\"" + s2 + "\",\"template\":\"empty\"}"))
                .andExpect(status().isOk()).andReturn());
        String t2id = t2.get("id").asText();
        assertEquals(s2, t2.get("streamId").asText());
        JsonNode st2 = state(admin, t2id);
        assertEquals(0, st2.get("tasks").size(), "empty template has no work items");
        assertEquals("Касса", st2.get("params").get("name").asText());

        // isolation: writing team-2 does not touch team-1 and vice versa
        mvc.perform(as(put("/api/state"), admin, t2id).content(stateWith("Задача кассы"))).andExpect(status().isOk());
        assertEquals("Задача кассы", state(admin, t2id).get("tasks").get(0).get("title").asText());
        assertEquals("Задача команды 1", state(admin, "t1").get("tasks").get(0).get("title").asText());
        // per-entity REST follows the same team context
        assertEquals("Задача кассы", json(mvc.perform(as(get("/api/tasks"), admin, t2id)).andExpect(status().isOk()).andReturn())
                .get(0).get("title").asText());

        // COPY template clones the source team's data
        String t3id = json(mvc.perform(as(post("/api/org/teams"), admin, null)
                .content("{\"name\":\"Клон\",\"streamId\":\"s1\",\"template\":\"copy\",\"source\":\"" + t2id + "\"}"))
                .andExpect(status().isOk()).andReturn()).get("id").asText();
        assertEquals("Задача кассы", state(admin, t3id).get("tasks").get(0).get("title").asText());

        // unknown team → 404
        mvc.perform(as(get("/api/state"), admin, "t404")).andExpect(status().isNotFound());

        // users without memberships keep their global role on every team
        String editor = login("editor", "editor123"), viewer = login("viewer", "viewer123");
        mvc.perform(as(put("/api/state"), editor, t2id).content(stateWith("E"))).andExpect(status().isOk());
        mvc.perform(as(put("/api/state"), viewer, t2id).content(stateWith("V"))).andExpect(status().isForbidden());
        mvc.perform(as(post("/api/org/streams"), editor, null).content("{\"name\":\"x\"}")).andExpect(status().isForbidden());

        // a membership narrows access: global VIEWER + EDITOR on team-2 only
        auth.create("anna", "Anna-pass-123", "VIEWER", "Анна");
        mvc.perform(as(post("/api/org/memberships"), admin, null)
                .content("{\"username\":\"anna\",\"scopeType\":\"TEAM\",\"scopeId\":\"" + t2id + "\",\"role\":\"EDITOR\"}"))
                .andExpect(status().isOk());
        String anna = login("anna", "Anna-pass-123");
        mvc.perform(as(put("/api/state"), anna, t2id).content(stateWith("A"))).andExpect(status().isOk());
        mvc.perform(as(get("/api/state"), anna, "t1")).andExpect(status().isForbidden());
        JsonNode annaOrg = json(mvc.perform(as(get("/api/org"), anna, null)).andExpect(status().isOk()).andReturn());
        assertEquals(1, annaOrg.get("teams").size());
        assertEquals("EDITOR", annaOrg.get("teams").get(0).get("role").asText());
        assertEquals(1, annaOrg.get("streams").size());
        assertFalse(annaOrg.get("canManage").asBoolean());

        // a STREAM membership opens every team of the stream (read-only here)
        auth.create("boris", "Boris-pass-123", "EDITOR", "Борис");
        mvc.perform(as(post("/api/org/memberships"), admin, null)
                .content("{\"username\":\"boris\",\"scopeType\":\"STREAM\",\"scopeId\":\"s1\",\"role\":\"VIEWER\"}"))
                .andExpect(status().isOk());
        String boris = login("boris", "Boris-pass-123");
        mvc.perform(as(get("/api/state"), boris, t3id)).andExpect(status().isOk());
        mvc.perform(as(put("/api/state"), boris, t3id).content(stateWith("B"))).andExpect(status().isForbidden());
        mvc.perform(as(get("/api/state"), boris, t2id)).andExpect(status().isForbidden());

        // deletion rules
        mvc.perform(as(delete("/api/org/teams/t1"), admin, null)).andExpect(status().isConflict());        // default team
        mvc.perform(as(delete("/api/org/streams/" + s2), admin, null)).andExpect(status().isConflict());  // not empty
        mvc.perform(as(delete("/api/org/teams/" + t3id), admin, null)).andExpect(status().isNoContent());
        mvc.perform(as(get("/api/state"), admin, t3id)).andExpect(status().isNotFound());
        assertEquals("Задача команды 1", state(admin, "t1").get("tasks").get(0).get("title").asText());
    }
}
