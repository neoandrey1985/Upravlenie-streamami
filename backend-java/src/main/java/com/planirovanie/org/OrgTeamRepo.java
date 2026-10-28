package com.planirovanie.org;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface OrgTeamRepo extends JpaRepository<OrgTeam, String> {
    List<OrgTeam> findAllByOrderByOrdAsc();
    List<OrgTeam> findByStreamId(String streamId);
}
