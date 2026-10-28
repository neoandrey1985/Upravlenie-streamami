package com.planirovanie.org;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.persistence.*;

import java.time.Instant;

@Entity
@Table(name = "org_streams")
@JsonIgnoreProperties(ignoreUnknown = true)
public class OrgStream {
    @Id public String id;
    @Column(nullable = false) public String name;
    public String descr;
    @Column(nullable = false) public int ord;
    @Column(name = "created_at") public Instant createdAt;
}
