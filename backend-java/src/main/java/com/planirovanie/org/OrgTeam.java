package com.planirovanie.org;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.*;

import java.time.Instant;

@Entity
@Table(name = "org_teams")
@JsonIgnoreProperties(ignoreUnknown = true)
public class OrgTeam {
    @Id public String id;
    @Column(name = "stream_id", nullable = false) @JsonProperty("streamId") public String streamId;
    @Column(nullable = false) public String name;
    @Column(name = "schema_name") @JsonIgnore public String schemaName;   // null = default schema
    @Column(nullable = false) public int ord;
    @Column(name = "created_at") public Instant createdAt;
}
