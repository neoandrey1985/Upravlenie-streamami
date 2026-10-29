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

/** Голос команды в оценке зрелости стрима: права на команду, слияние в документ стрима, версия. */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "app.auth.enabled=true",
        "app.auth.seed-defaults=true",
        "spring.datasource.url=jdbc:h2:mem:streams_vote;MODE=PostgreSQL;DB_CLOSE_DELAY=-1"
})
class MaturityVoteTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper om;
    @Autowired AuthService auth;

    private JsonNode json(MvcResult r) throws Exception { return om.readTree(r.getResponse().getContentAsString(StandardCharsets.UTF_8)); }

    private String login(String user, String pass) throws Exception {
        return json(mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + user + "\",\"password\":\"" + pass + "\"}")).andExpect(status().isOk()).andReturn()).get("token").asText();
    }

    private static MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder b, String token) {
        return b.header("Authorization", "Bearer " + token).contentType(MediaType.APPLICATION_JSON);
    }

    private static String vote(String team, String dim, int level) {
        return "{\"team\":\"" + team + "\",\"pi\":\"PI-1\",\"votes\":{\"" + dim + "\":" + level + "}}";
    }

    @Test
    void teamMembersVoteForTheirTeamOnly() throws Exception {
        String admin = login("admin", "admin123");
        mvc.perform(as(put("/api/org/streams/s1/doc"), admin).content("{\"baseVersion\":0,\"data\":{\"features\":[{\"id\":\"F-1\",\"name\":\"Фича\"}]}}"))
           .andExpect(status().isOk());
        String t2 = json(mvc.perform(as(post("/api/org/teams"), admin).content("{\"name\":\"Вторая\",\"streamId\":\"s1\",\"template\":\"empty\"}"))
                .andExpect(status().isOk()).andReturn()).get("id").asText();
        auth.create("dev", "Dev-pass-1234", "VIEWER", "Dev");
        mvc.perform(as(post("/api/org/memberships"), admin).content("{\"username\":\"dev\",\"scopeType\":\"TEAM\",\"scopeId\":\"t1\",\"role\":\"EDITOR\"}"))
           .andExpect(status().isOk());
        String dev = login("dev", "Dev-pass-1234"), viewer = login("viewer", "viewer123");

        // участник команды голосует за свою команду; документ стрима сохраняет остальные данные, версия растёт
        JsonNode r = json(mvc.perform(as(post("/api/org/streams/s1/vote"), dev).content(vote("t1", "pi", 3))).andExpect(status().isOk()).andReturn());
        assertEquals(2, r.get("version").asLong());
        assertEquals(3, r.get("data").get("mat").get("rounds").get(0).get("votes").get("pi").get("t1").asInt());
        assertEquals("Фича", r.get("data").get("features").get(0).get("name").asText());
        // повторный голос перезаписывает, 0 — снимает
        mvc.perform(as(post("/api/org/streams/s1/vote"), dev).content(vote("t1", "pi", 4))).andExpect(status().isOk());
        JsonNode doc = json(mvc.perform(as(get("/api/org/streams/s1/doc"), admin)).andExpect(status().isOk()).andReturn());
        assertEquals(4, doc.get("data").get("mat").get("rounds").get(0).get("votes").get("pi").get("t1").asInt());
        assertEquals(1, doc.get("data").get("mat").get("rounds").size());

        // нельзя: за чужую команду, без прав на запись, неверный уровень, команда не из этого стрима
        mvc.perform(as(post("/api/org/streams/s1/vote"), dev).content(vote(t2, "pi", 2))).andExpect(status().isForbidden());
        mvc.perform(as(post("/api/org/streams/s1/vote"), viewer).content(vote("t1", "pi", 2))).andExpect(status().isForbidden());
        mvc.perform(as(post("/api/org/streams/s1/vote"), dev).content(vote("t1", "pi", 7))).andExpect(status().isBadRequest());
        String s2 = json(mvc.perform(as(post("/api/org/streams"), admin).content("{\"name\":\"Другой\"}")).andExpect(status().isOk()).andReturn()).get("id").asText();
        mvc.perform(as(post("/api/org/streams/" + s2 + "/vote"), admin).content(vote("t1", "pi", 2))).andExpect(status().isBadRequest());
        // участник команды по-прежнему не может править документ стрима целиком
        mvc.perform(as(put("/api/org/streams/s1/doc"), dev).content("{\"data\":{}}")).andExpect(status().isForbidden());
        // голос сдвинул версию: устаревшая запись RTE получает 409
        mvc.perform(as(put("/api/org/streams/s1/doc"), admin).content("{\"baseVersion\":1,\"data\":{}}")).andExpect(status().isConflict());
    }
}
