package com.planirovanie.org;

import jakarta.persistence.*;

import java.time.Instant;

@Entity
@Table(name = "org_stream_docs")
public class OrgStreamDoc {
    @Id @Column(name = "stream_id") public String streamId;
    @Column(nullable = false) public long version;
    @Column(columnDefinition = "text") public String data;
    @Column(name = "updated_at") public Instant updatedAt;
    @Column(name = "updated_by") public String updatedBy;
}
