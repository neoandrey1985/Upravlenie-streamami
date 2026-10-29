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

/** Команда управления стрима: лидер и ИТ-лидер правят стрим и команды, архитектор и ПМ — только данные стрима. */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "app.auth.enabled=true",
        "app.auth.seed-defaults=true",
        "spring.datasource.url=jdbc:h2:mem:streams_pos;MODE=PostgreSQL;DB_CLOSE_DELAY=-1"
})
class StreamPositionsTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper om;
    @Autowired AuthService auth;

    private JsonNode json(MvcResult r) throws Exception { return om.readTree(r.getResponse().getContentAsString(StandardCharsets.UTF_8)); }

    private String login(String user, String pass) throws Exception {
        return json(mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + user + "\",\"password\":\"" + pass + "\"}")).andExpect(status().isOk()).andReturn()).get("token").asText();
    }

    private static MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder b, String token, String team) {
        b.header("Authorization", "Bearer " + token);
        if (team != null) b.header("X-Team-Id", team);
        return b.contentType(MediaType.APPLICATION_JSON);
    }

    private static final String STATE = "{\"state\":{\"params\":{\"name\":\"N\",\"start\":\"2026-08-03\",\"sprintDays\":10,\"focus\":0.8,\"today\":\"2026-09-10\",\"goal\":\"G\",\"sprints\":11},\"tasks\":[]}}";

    private void appoint(String admin, String user, String position, int expected) throws Exception {
        mvc.perform(as(post("/api/org/memberships"), admin, null)
                .content("{\"username\":\"" + user + "\",\"scopeType\":\"STREAM\",\"scopeId\":\"s1\",\"role\":\"VIEWER\",\"position\":\"" + position + "\"}"))
           .andExpect(status().is(expected));
    }

    @Test
    void managementTeamPositionsAndRights() throws Exception {
        String admin = login("admin", "admin123");
        for (String[] u : new String[][]{{"lead", "Петрова М."}, {"itlead", "Смирнов К."}, {"arch", "Кузнецова Е."}, {"pm", "Орлов Д."}})
            auth.create(u[0], "Pass-" + u[0] + "-1234", "VIEWER", u[1]);
        appoint(admin, "lead", "LEAD", 200); appoint(admin, "itlead", "ITLEAD", 200);
        appoint(admin, "arch", "ARCH", 200); appoint(admin, "pm", "PM", 200);
        appoint(admin, "pm", "RTE", 400);                                                    // неизвестная должность
        mvc.perform(as(post("/api/org/memberships"), admin, null)
                .content("{\"username\":\"pm\",\"scopeType\":\"TEAM\",\"scopeId\":\"t1\",\"role\":\"EDITOR\",\"position\":\"PM\"}"))
           .andExpect(status().isBadRequest());                                               // должность — только у стрима

        // состав команды управления виден в оргструктуре (с именами пользователей)
        JsonNode s1 = json(mvc.perform(as(get("/api/org"), admin, null)).andExpect(status().isOk()).andReturn()).get("streams").get(0);
        assertEquals(4, s1.get("mgmt").size());
        assertEquals("Лидер стрима", s1.get("mgmt").get(0).get("title").asText());
        assertEquals("Петрова М.", s1.get("mgmt").get(0).get("name").asText());

        String lead = login("lead", "Pass-lead-1234"), itlead = login("itlead", "Pass-itlead-1234"),
               arch = login("arch", "Pass-arch-1234"), pm = login("pm", "Pass-pm-1234");
        // все четверо правят данные стрима
        long v = 0;
        for (String tk : new String[]{lead, itlead, arch, pm}) {
            v = json(mvc.perform(as(put("/api/org/streams/s1/doc"), tk, null).content("{\"baseVersion\":" + v + ",\"data\":{\"features\":[]}}"))
                    .andExpect(status().isOk()).andReturn()).get("version").asLong();
        }
        // лидеры правят команды стрима, архитектор и ПМ — только просмотр команд
        mvc.perform(as(put("/api/state"), lead, "t1").content(STATE)).andExpect(status().isOk());
        mvc.perform(as(put("/api/state"), itlead, "t1").content(STATE)).andExpect(status().isOk());
        mvc.perform(as(get("/api/state"), arch, "t1")).andExpect(status().isOk());
        mvc.perform(as(put("/api/state"), arch, "t1").content(STATE)).andExpect(status().isForbidden());
        mvc.perform(as(put("/api/state"), pm, "t1").content(STATE)).andExpect(status().isForbidden());
        JsonNode pmOrg = json(mvc.perform(as(get("/api/org"), pm, null)).andExpect(status().isOk()).andReturn());
        assertEquals("VIEWER", pmOrg.get("teams").get(0).get("role").asText());
        // должность снимается удалением назначения
        JsonNode all = json(mvc.perform(as(get("/api/org/memberships"), admin, null)).andExpect(status().isOk()).andReturn());
        long pk = 0;
        for (JsonNode m : all) if ("arch".equals(m.get("username").asText())) { pk = m.get("pk").asLong(); assertEquals("ARCH", m.get("position").asText()); }
        mvc.perform(as(delete("/api/org/memberships/" + pk), admin, null)).andExpect(status().isNoContent());
        assertEquals(3, json(mvc.perform(as(get("/api/org"), admin, null)).andReturn()).get("streams").get(0).get("mgmt").size());
    }
}
