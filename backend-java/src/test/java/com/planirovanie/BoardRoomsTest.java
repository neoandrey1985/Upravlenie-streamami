package com.planirovanie;

import com.planirovanie.web.BoardSocketHandler;
import org.junit.jupiter.api.Test;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/** Whiteboard rooms are per team: board ops, presence and leave never cross team boundaries. */
class BoardRoomsTest {

    private WebSocketSession fake(List<String> sink, String name, String team) {
        WebSocketSession s = mock(WebSocketSession.class);
        when(s.isOpen()).thenReturn(true);
        Map<String, Object> attrs = new HashMap<>();
        attrs.put("name", name);
        attrs.put("team", team);
        when(s.getAttributes()).thenReturn(attrs);
        try {
            doAnswer(inv -> { sink.add(((TextMessage) inv.getArgument(0)).getPayload()); return null; })
                .when(s).sendMessage(any());
        } catch (Exception ignore) {}
        return s;
    }

    @Test
    void roomsArePerTeam() throws Exception {
        BoardSocketHandler h = new BoardSocketHandler();
        List<String> ann = new ArrayList<>(), bob = new ArrayList<>(), eve = new ArrayList<>();
        WebSocketSession a = fake(ann, "Ann", "t1"), b = fake(bob, "Bob", "t1"), e = fake(eve, "Eve", "t2");
        h.afterConnectionEstablished(a);
        h.afterConnectionEstablished(e);
        h.afterConnectionEstablished(b);

        // presence: Ann sees Bob join, Eve (other team) does not; Bob's welcome lists Ann but not Eve
        assertTrue(ann.stream().anyMatch(m -> m.contains("\"type\":\"join\"") && m.contains("Bob")));
        assertFalse(eve.stream().anyMatch(m -> m.contains("Bob") || m.contains("Ann")));
        String welcome = bob.stream().filter(m -> m.contains("\"type\":\"welcome\"")).findFirst().orElseThrow();
        assertTrue(welcome.contains("Ann"));
        assertFalse(welcome.contains("Eve"));

        // ops stay inside the room
        h.handleTextMessage(a, new TextMessage("{\"type\":\"op\",\"op\":\"upsert\",\"item\":{\"id\":\"x1\",\"t\":\"sticky\"}}"));
        assertTrue(bob.stream().anyMatch(m -> m.contains("x1")));
        assertFalse(eve.stream().anyMatch(m -> m.contains("x1")), "another team must not receive the op");

        // leave reaches only the team mates, even though the session is unregistered first
        h.afterConnectionClosed(a, CloseStatus.NORMAL);
        assertTrue(bob.stream().anyMatch(m -> m.contains("\"type\":\"leave\"")));
        assertFalse(eve.stream().anyMatch(m -> m.contains("\"type\":\"leave\"")));
    }
}
