package com.planirovanie.org;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.*;

@Entity
@Table(name = "org_memberships")
@JsonIgnoreProperties(ignoreUnknown = true)
public class OrgMembership {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long pk;
    @Column(nullable = false) public String username;
    @Column(name = "scope_type", nullable = false) @JsonProperty("scopeType") public String scopeType;  // STREAM | TEAM
    @Column(name = "scope_id", nullable = false) @JsonProperty("scopeId") public String scopeId;
    @Column(nullable = false) public String role;                                                   // VIEWER | EDITOR
}
